from pathlib import Path

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.semantics import (
    AggregateOperator,
    AggregateSpec,
    BindingStatus,
    SemanticBinding,
)
from agentic_text2sql.contracts.sql import (
    CandidateRecord,
    CandidateSelection,
    DirectRunResult,
    DirectStatus,
    SqlCandidate,
)
from agentic_text2sql.layer3_generation.easy_compiler import (
    GROUNDED_EASY_COMPILER_MODEL,
    GROUNDED_EASY_COMPILER_VERSION,
)
from agentic_text2sql.layer6_application.champion_challenger import (
    CandidateArbitrator,
    ChallengerDeadlineExceeded,
    ChampionChallengerService,
    admits_adaptive_intervention,
)


def result(
    status: DirectStatus,
    *,
    rows: list[list[object]] | None = None,
    proven: bool = False,
    sql: str | None = None,
) -> DirectRunResult:
    if proven and status is DirectStatus.SUCCEEDED and sql is None:
        sql = "SELECT COUNT(*) FROM orders"
    binding = SemanticBinding(
        db_id="synthetic",
        catalog_hash="catalog1",
        status=BindingStatus.PROVEN,
        aggregate=AggregateSpec(
            operator=AggregateOperator.COUNT_ROWS,
            table="orders",
            evidence_id="semantic.entity.orders",
            source_grain="one row per order_id",
        ),
        required_tables=("orders",),
        rule_ids=("entity.orders",),
    )
    return DirectRunResult(
        run_id=status.value,
        question="How many orders?",
        status=status,
        route_reason="query",
        prompt_versions={},
        plan=({"semantic_links": {"binding": binding.model_dump(mode="json")}} if proven else None),
        plan_validation={"accepted": True} if proven else None,
        candidate=(
            CandidateRecord(
                candidate=SqlCandidate(sql=sql, confidence=1),
                normalized_sql=sql,
                fingerprint="a" * 64,
                model_name=GROUNDED_EASY_COMPILER_MODEL if proven else "fake",
                prompt_version=GROUNDED_EASY_COMPILER_VERSION if proven else "test",
                catalog_hash="catalog1",
            )
            if sql is not None
            else None
        ),
        result_rows=rows or [],
        latency_ms={"total": 5},
    )


def test_shadow_never_changes_an_incumbent_output() -> None:
    incumbent = result(DirectStatus.SUCCEEDED, rows=[[4]])
    challenger = result(DirectStatus.SUCCEEDED, rows=[[5]], proven=True)
    decision = CandidateArbitrator(frozenset({"aggregate:count_rows"})).decide(
        incumbent, challenger, mode="shadow", elapsed_ms=10
    )
    assert decision.selection is CandidateSelection.KEEP_INCUMBENT
    assert decision.reason == "SHADOW_MODE_NEVER_CHANGES_OUTPUT"
    assert decision.incumbent_result_rows == [[4]]
    assert decision.challenger_result_rows == [[5]]


def test_enforce_promotes_only_certified_proof_over_terminal_incumbent() -> None:
    incumbent = result(DirectStatus.MODEL_ERROR)
    challenger = result(DirectStatus.SUCCEEDED, rows=[[4]], proven=True)
    uncertified = CandidateArbitrator().decide(incumbent, challenger, mode="enforce", elapsed_ms=10)
    certified = CandidateArbitrator(frozenset({"aggregate:count_rows"})).decide(
        incumbent, challenger, mode="enforce", elapsed_ms=10
    )
    accepted_incumbent = CandidateArbitrator(frozenset({"aggregate:count_rows"})).decide(
        result(DirectStatus.SUCCEEDED, rows=[[3]]),
        challenger,
        mode="enforce",
        elapsed_ms=10,
    )
    assert uncertified.selection is CandidateSelection.KEEP_INCUMBENT
    assert uncertified.reason == "UNCERTIFIED_PROOF_KIND:aggregate:count_rows"
    assert certified.selection is CandidateSelection.PROMOTE_CHALLENGER
    assert accepted_incumbent.selection is CandidateSelection.KEEP_INCUMBENT
    assert accepted_incumbent.reason == "INCUMBENT_ALREADY_ACCEPTED"


def test_enforce_can_replace_successful_incumbent_only_on_typed_contradiction() -> None:
    incumbent = result(
        DirectStatus.SUCCEEDED,
        rows=[[4]],
        sql="SELECT COUNT(*) FROM order_summaries",
    )
    challenger = result(
        DirectStatus.SUCCEEDED,
        rows=[[5]],
        proven=True,
        sql="SELECT COUNT(*) FROM orders",
    )

    decision = CandidateArbitrator(frozenset({"aggregate:count_rows"})).decide(
        incumbent, challenger, mode="enforce", elapsed_ms=10
    )

    assert decision.selection is CandidateSelection.PROMOTE_CHALLENGER
    assert decision.incumbent_contradictions == ("TYPED_OWNER_MISSING",)
    assert decision.reason.startswith("CERTIFIED_CHALLENGER_REPAIRS_CONTRADICTION")


def test_arbitration_rejects_model_rewrite_and_sql_that_contradicts_proof() -> None:
    incumbent = result(DirectStatus.MODEL_ERROR)
    rewritten = result(
        DirectStatus.SUCCEEDED,
        rows=[[4]],
        proven=True,
        sql="SELECT COUNT(*) FROM orders",
    )
    assert rewritten.candidate is not None
    rewritten = rewritten.model_copy(
        update={
            "candidate": rewritten.candidate.model_copy(
                update={"model_name": "model-corrector", "prompt_version": "corrector-v1"}
            )
        }
    )
    contradictory = result(
        DirectStatus.SUCCEEDED,
        rows=[[4]],
        proven=True,
        sql="SELECT MAX(order_id) FROM orders",
    )
    arbitrator = CandidateArbitrator(frozenset({"aggregate:count_rows"}))

    rewritten_decision = arbitrator.decide(incumbent, rewritten, mode="shadow", elapsed_ms=10)
    contradictory_decision = arbitrator.decide(
        incumbent, contradictory, mode="shadow", elapsed_ms=10
    )

    assert not rewritten_decision.challenger_proof_accepted
    assert rewritten_decision.reason == "CHALLENGER_NOT_DETERMINISTIC_PROOF_COMPILER"
    assert not contradictory_decision.challenger_proof_accepted
    assert contradictory_decision.reason == "CHALLENGER_SQL_CONTRADICTS_PROOF"
    assert contradictory_decision.challenger_contradictions == ("TYPED_AGGREGATE_MISMATCH",)


class StubRuntime:
    def __init__(self, output: DirectRunResult) -> None:
        self.output = output
        self.calls = 0

    def run(self, question: str, database: Path, catalog: CatalogSnapshot) -> DirectRunResult:
        del question, database, catalog
        self.calls += 1
        return self.output


class PlanAwareStubRuntime(StubRuntime):
    def __init__(self, output: DirectRunResult) -> None:
        super().__init__(output)
        self.reused_plan: object | None = None

    def run_from_baseline_plan(
        self,
        question: str,
        database: Path,
        catalog: CatalogSnapshot,
        baseline_plan: object,
    ) -> DirectRunResult:
        del question, database, catalog
        self.calls += 1
        self.reused_plan = baseline_plan
        return self.output


class Clock:
    def __init__(self, values: list[float]) -> None:
        self.values = iter(values)

    def __call__(self) -> float:
        return next(self.values)


def test_deadline_admission_skips_challenger_and_records_reason() -> None:
    incumbent = StubRuntime(result(DirectStatus.SUCCEEDED, rows=[[4]]))
    challenger = StubRuntime(result(DirectStatus.SUCCEEDED, rows=[[5]], proven=True))
    service = ChampionChallengerService(
        incumbent=incumbent,
        challenger=challenger,
        mode="shadow",
        total_deadline_seconds=60,
        minimum_challenger_seconds=20,
        arbitrator=CandidateArbitrator(),
        monotonic=Clock([0, 45]),
    )

    output = service.run(
        "How many orders?",
        Path("unused"),
        CatalogSnapshot(db_id="synthetic", dialect="sqlite", tables=[], catalog_hash="catalog1"),
    )

    assert output.result_rows == [[4]]
    assert output.arbitration is not None
    assert output.arbitration.selection is CandidateSelection.SKIP_CHALLENGER
    assert challenger.calls == 0


def test_shadow_wrapper_persists_both_results_but_returns_incumbent() -> None:
    incumbent = StubRuntime(result(DirectStatus.SUCCEEDED, rows=[[4]]))
    challenger = StubRuntime(result(DirectStatus.SUCCEEDED, rows=[[5]], proven=True))
    service = ChampionChallengerService(
        incumbent=incumbent,
        challenger=challenger,
        mode="shadow",
        total_deadline_seconds=60,
        minimum_challenger_seconds=20,
        arbitrator=CandidateArbitrator(),
        monotonic=Clock([0, 5, 10]),
    )

    output = service.run(
        "How many orders?",
        Path("unused"),
        CatalogSnapshot(db_id="synthetic", dialect="sqlite", tables=[], catalog_hash="catalog1"),
    )

    assert output.result_rows == [[4]]
    assert output.arbitration is not None
    assert output.arbitration.challenger_result_rows == [[5]]
    assert output.arbitration.challenger_proof_kind == "aggregate:count_rows"
    assert output.latency_ms["champion_challenger_total"] == 10000


def test_admission_skips_baseline_preserve_without_running_challenger() -> None:
    baseline = result(DirectStatus.SUCCEEDED, rows=[[4]]).model_copy(
        update={
            "plan": {
                "question_language": "en",
                "task_type": "aggregation",
                "metrics": ["order count"],
                "required_concepts": ["orders"],
            }
        }
    )
    incumbent = StubRuntime(baseline)
    challenger = StubRuntime(result(DirectStatus.SUCCEEDED, rows=[[5]], proven=True))
    service = ChampionChallengerService(
        incumbent=incumbent,
        challenger=challenger,
        mode="shadow",
        total_deadline_seconds=60,
        minimum_challenger_seconds=20,
        arbitrator=CandidateArbitrator(),
        admission=admits_adaptive_intervention,
        monotonic=Clock([0, 5]),
    )

    output = service.run(
        "How many orders?",
        Path("unused"),
        CatalogSnapshot(db_id="synthetic", dialect="sqlite", tables=[], catalog_hash="catalog1"),
    )

    assert output.arbitration is not None
    assert output.arbitration.selection is CandidateSelection.SKIP_CHALLENGER
    assert output.arbitration.reason == "NO_PROVEN_SEMANTIC_INTERVENTION"
    assert challenger.calls == 0


def test_admitted_challenger_reuses_incumbent_control_plan() -> None:
    baseline = result(DirectStatus.SUCCEEDED, rows=[[4]]).model_copy(
        update={
            "plan": {
                "question_language": "en",
                "task_type": "set",
                "metrics": ["order count"],
                "required_concepts": ["orders"],
            }
        }
    )
    incumbent = StubRuntime(baseline)
    challenger = PlanAwareStubRuntime(result(DirectStatus.SUCCEEDED, rows=[[5]], proven=True))
    service = ChampionChallengerService(
        incumbent=incumbent,
        challenger=challenger,
        mode="shadow",
        total_deadline_seconds=60,
        minimum_challenger_seconds=20,
        arbitrator=CandidateArbitrator(),
        admission=admits_adaptive_intervention,
        monotonic=Clock([0, 5, 10]),
    )

    service.run(
        "Orders without payments",
        Path("unused"),
        CatalogSnapshot(db_id="synthetic", dialect="sqlite", tables=[], catalog_hash="catalog1"),
    )

    assert challenger.calls == 1
    assert challenger.reused_plan is not None


def test_challenger_deadline_becomes_typed_skip_without_losing_incumbent() -> None:
    class DeadlineRuntime(StubRuntime):
        def run(self, question: str, database: Path, catalog: CatalogSnapshot) -> DirectRunResult:
            del question, database, catalog
            raise ChallengerDeadlineExceeded

    incumbent = StubRuntime(result(DirectStatus.SUCCEEDED, rows=[[4]]))
    service = ChampionChallengerService(
        incumbent=incumbent,
        challenger=DeadlineRuntime(result(DirectStatus.SUCCEEDED)),
        mode="shadow",
        total_deadline_seconds=60,
        minimum_challenger_seconds=20,
        arbitrator=CandidateArbitrator(),
        monotonic=Clock([0, 5, 10]),
    )

    output = service.run(
        "How many orders?",
        Path("unused"),
        CatalogSnapshot(db_id="synthetic", dialect="sqlite", tables=[], catalog_hash="catalog1"),
    )

    assert output.result_rows == [[4]]
    assert output.arbitration is not None
    assert output.arbitration.selection is CandidateSelection.SKIP_CHALLENGER
    assert output.arbitration.reason == "CHALLENGER_DEADLINE_EXHAUSTED"
