from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from agentic_text2sql.adapters.llm.ollama_provider import OllamaProvider
from agentic_text2sql.contracts.assessment import CheckOutcome, ClauseFinding, ModelCritique
from agentic_text2sql.contracts.sql import DirectStatus, SqlCandidate
from agentic_text2sql.exceptions import ConfigurationError, StructuredOutputError
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer3_generation.a1_prompt import build_evidence
from agentic_text2sql.layer3_generation.sql_text_adapter import sql_text_candidate
from agentic_text2sql.layer4_validation.clause_critic import assess_clauses
from agentic_text2sql.layer6_application.a1_service import A1QueryService, grounded_model_findings
from agentic_text2sql.settings import Settings
from agentic_text2sql.workflow.budgets import BudgetExceededError, RequestBudget, request_scope


class QueueProvider:
    def __init__(self, responses: list[BaseModel | Exception]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def generate_structured(
        self, *, prompt: str, response_model: type[BaseModel], model: str | None = None
    ) -> Any:
        del response_model, model
        self.prompts.append(prompt)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture()
def database(tmp_path: Path) -> Path:
    path = tmp_path / "tiny.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE teams(id INTEGER PRIMARY KEY, label TEXT);
            CREATE TABLE scores(id INTEGER PRIMARY KEY,
                team INTEGER REFERENCES teams(id), score INT);
            CREATE TABLE awards(id INTEGER PRIMARY KEY,
                team INTEGER REFERENCES teams(id), prize INT);
            INSERT INTO teams VALUES (1, 'alpha'), (2, 'beta');
            INSERT INTO scores VALUES (1,1,10), (2,1,10), (3,2,5);
            INSERT INTO awards VALUES (1,1,1), (2,1,2), (3,1,3);
        """)
    return path


def run(
    database: Path,
    provider: QueueProvider,
    *,
    mode: str = "off",
    question: str = "Show the top 1 highest scores",
    correction: bool = False,
) -> Any:
    settings = Settings(TEXT2SQL_PIPELINE_MODE="a1", TEXT2SQL_CRITIC_MODE=mode)
    catalog = SQLiteIntrospector().inspect(database, "tiny")
    return A1QueryService(provider, settings, correction_enabled=correction).run(
        question, database, catalog
    )


def test_a1_first_pass_uses_one_call_no_plan_and_retains_evidence(database: Path) -> None:
    provider = QueueProvider([SqlCandidate(sql="SELECT COUNT(*) FROM scores", confidence=1)])
    result = run(database, provider, question="How many scores are there?")
    assert result.status is DirectStatus.SUCCEEDED
    assert result.result_rows == [[3]]
    assert len(provider.prompts) == 1
    assert result.plan is None
    assert result.assessment["actual_generation_requests"] == 1
    assert result.assessment["semantic_status"] == "UNVERIFIED"
    assert "PRIMARY KEY" in provider.prompts[0]
    assert "FOREIGN KEY" in provider.prompts[0]


@pytest.mark.parametrize(
    "cpu,routing,requests",
    [
        (True, True, 1),
        (False, True, 2),
        (True, False, 2),
        (False, False, 3),
    ],
)
def test_contract_controls_isolate_routing_and_repair_backend(
    database: Path,
    cpu: bool,
    routing: bool,
    requests: int,
) -> None:
    responses: list[BaseModel | Exception] = [
        SqlCandidate(sql="SELECT score FROM scores LIMIT 3", confidence=0),
    ]
    if not routing:
        responses.append(ModelCritique())
    if not cpu:
        responses.append(
            SqlCandidate(
                sql='SELECT score FROM scores ORDER BY "scores"."score" DESC LIMIT 1',
                confidence=0,
            )
        )
    provider = QueueProvider(responses)
    settings = Settings(
        TEXT2SQL_PIPELINE_MODE="a1",
        TEXT2SQL_CRITIC_MODE="repair",
        TEXT2SQL_COMPUTE_POLICY="obligation",
        TEXT2SQL_DETERMINISTIC_REPAIR=cpu,
        TEXT2SQL_REPAIRABILITY_ROUTING=routing,
        TEXT2SQL_A1_MAX_REQUESTS=requests,
    )
    result = A1QueryService(provider, settings, correction_enabled=True).run(
        "Show top 1 highest scores",
        database,
        SQLiteIntrospector().inspect(database, "tiny"),
    )
    assert result.result_rows == [[10]]
    assert result.assessment["repair_admitted"]
    assert result.assessment["actual_generation_requests"] == requests
    assert result.assessment["critic_routed"] is not routing
    assert result.assessment["evaluations"][-1]["origin"] == ("deterministic" if cpu else "model")
    assert result.assessment["semantic_status"] == "UNVERIFIED"


def test_shadow_does_not_change_draft_even_when_critic_disagrees(database: Path) -> None:
    sql = "SELECT score FROM scores ORDER BY score ASC LIMIT 1"
    finding = ClauseFinding(
        code="bad",
        clause="SELECT",
        outcome=CheckOutcome.CONTRADICTION,
        message="Incorrect selection",
        evidence_ids=("question",),
        question_span="scores",
        source="deterministic",
    )
    provider = QueueProvider(
        [SqlCandidate(sql=sql, confidence=1), ModelCritique(findings=[finding])]
    )
    result = run(database, provider, mode="shadow")
    assert result.candidate.normalized_sql.endswith("ASC LIMIT 1")
    assert result.assessment["model_findings"][0]["source"] == "model"
    assert not result.assessment["repair_attempted"]
    assert len(provider.prompts) == 2


def test_repair_admission_and_failed_repair_retention(database: Path) -> None:
    draft = SqlCandidate(sql="SELECT score FROM scores ORDER BY score ASC LIMIT 1", confidence=1)
    repair = SqlCandidate(sql="SELECT score FROM scores ORDER BY score DESC LIMIT 1", confidence=0)
    result = run(
        database, QueueProvider([draft, ModelCritique(), repair]), mode="repair", correction=True
    )
    assert result.result_rows == [[10]]
    assert result.assessment["repair_admitted"]
    assert result.assessment["actual_generation_requests"] == 3
    result = run(
        database,
        QueueProvider([draft, ModelCritique(), StructuredOutputError("bad format")]),
        mode="repair",
        correction=True,
    )
    assert result.result_rows == [[5]]
    assert not result.assessment["repair_admitted"]
    assert result.assessment["selection_reason"] == "draft_retained_repair_error"


def test_no_repair_without_explicit_correction_flag(database: Path) -> None:
    draft = SqlCandidate(sql="SELECT score FROM scores ORDER BY score ASC LIMIT 1", confidence=1)
    result = run(database, QueueProvider([draft, ModelCritique()]), mode="repair")
    assert result.assessment["actual_generation_requests"] == 2
    assert not result.assessment["repair_attempted"]


def test_operational_unknown_column_repair_skips_semantic_critic(database: Path) -> None:
    provider = QueueProvider(
        [
            SqlCandidate(sql="SELECT missing FROM scores", confidence=0),
            SqlCandidate(sql="SELECT score FROM scores", confidence=0),
        ]
    )
    result = run(database, provider, mode="repair", correction=True, question="Show scores")
    assert result.status is DirectStatus.SUCCEEDED
    assert result.assessment["repair_reason"] == "operational_error"
    assert result.assessment["repair_admitted"]
    assert result.assessment["actual_generation_requests"] == 2
    assert not result.assessment["critic_routed"]
    assert len(result.assessment["evaluations"]) == 2
    assert result.assessment["evaluations"][0]["raw_sql"] == "SELECT missing FROM scores"


def test_write_candidate_is_never_repaired_or_executed(database: Path) -> None:
    provider = QueueProvider([SqlCandidate(sql="DELETE FROM scores", confidence=0)])
    result = run(database, provider, mode="repair", correction=True, question="Show scores")
    assert result.status is DirectStatus.POLICY_BLOCKED
    assert len(provider.prompts) == 1
    assert not result.assessment["repair_attempted"]


def test_fenced_json_candidate_uses_normalized_policy_path(database: Path) -> None:
    candidate = SqlCandidate(sql="```sql\nSELECT score FROM scores\n```", confidence=0)
    result = run(database, QueueProvider([candidate]), question="Show scores")
    assert result.status is DirectStatus.SUCCEEDED
    assert result.assessment["evaluations"][0]["raw_sql"].startswith("```sql")
    assert result.assessment["executed_sql"].endswith("LIMIT 200")


def test_native_sql_pipeline_uses_one_budgeted_request(database: Path) -> None:
    class TextProvider(QueueProvider):
        def generate_sql_text(self, *, prompt: str, model: str | None = None) -> str:
            del model
            self.prompts.append(prompt)
            return "```sql\nSELECT COUNT(*) FROM scores\n```"

    provider = TextProvider([])
    settings = Settings(TEXT2SQL_PIPELINE_MODE="a1", TEXT2SQL_GENERATION_FORMAT="sql_text")
    result = A1QueryService(provider, settings).run(
        "Count scores", database, SQLiteIntrospector().inspect(database, "tiny")
    )
    assert result.status is DirectStatus.SUCCEEDED
    assert result.assessment["actual_generation_requests"] == 1
    assert result.result_rows == [[3]]
    assert "Database schema:" in provider.prompts[0]
    assert "Return JSON" not in provider.prompts[0]
    assert result.assessment["prompts"]["draft"]["rendered_prompt"] == provider.prompts[0]


def test_implicit_foreign_key_target_resolves_declared_primary_key(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE implicit_child(id INTEGER PRIMARY KEY, team REFERENCES teams)"
        )
    catalog = SQLiteIntrospector().inspect(database, "tiny")
    evidence = build_evidence("Count teams", catalog, None, "")
    child = next(item.text for item in evidence if item.evidence_id == "catalog:implicit_child")
    assert 'REFERENCES "teams" ("id")' in child
    assert '"None"' not in child


def test_missing_order_cannot_be_admitted_without_metric_binding(database: Path) -> None:
    provider = QueueProvider(
        [
            SqlCandidate(sql="SELECT score FROM scores LIMIT 1", confidence=0),
            ModelCritique(),
            SqlCandidate(sql="SELECT score FROM scores ORDER BY score DESC LIMIT 1", confidence=0),
        ]
    )
    result = run(database, provider, mode="repair", correction=True)
    assert not result.assessment["repair_admitted"]
    assert result.assessment["selection_reason"] == "draft_retained_repair_not_admitted"


def test_shadow_sample_is_deterministic_and_does_not_depend_on_gold(database: Path) -> None:
    from agentic_text2sql.contracts.assessment import CandidateEvaluation
    from agentic_text2sql.contracts.validation import PolicyDecision, ValidationReport
    from agentic_text2sql.layer4_validation.critic_router import route_critic

    evaluation = CandidateEvaluation(
        raw_sql="SELECT COUNT(*) FROM scores",
        policy=PolicyDecision(allowed=True),
        validation=ValidationReport(accepted=True),
        checks=assess_clauses(
            "Count scores",
            "SELECT COUNT(*) FROM scores",
            SQLiteIntrospector().inspect(database, "tiny"),
        ),
    )
    off = route_critic("Count scores", evaluation, enabled=True, shadow_sample_rate=0)
    on = route_critic("Count scores", evaluation, enabled=True, shadow_sample_rate=1)
    assert not off.call_critic
    assert on.call_critic and on.shadow_sample
    assert on == route_critic("Count scores", evaluation, enabled=True, shadow_sample_rate=1)


@pytest.mark.parametrize(
    "question,sql",
    [
        ("Show the top 1 highest scores", "SELECT score FROM scores ORDER BY score DESC LIMIT 1"),
        ("Show the bottom 1 lowest scores", "SELECT score FROM scores ORDER BY score ASC LIMIT 1"),
        ("Do not show the top 1 scores", "SELECT score FROM scores"),
        ("Show the top 1 scores including ties", "SELECT score FROM scores"),
        ("What is the maximum score?", "SELECT MAX(score) FROM scores"),
        ("Show the top 1 highest scores", "SELECT score FROM (SELECT score FROM scores) LIMIT 1"),
    ],
)
def test_correct_and_out_of_scope_queries_do_not_trigger_contradictions(
    database: Path, question: str, sql: str
) -> None:
    assessment = assess_clauses(question, sql, SQLiteIntrospector().inspect(database, "tiny"))
    assert not assessment.contradictions
    assert assessment.semantic_status == "UNVERIFIED"


def test_renamed_sibling_fanout_is_unknown_and_real_counterexample(database: Path) -> None:
    catalog = SQLiteIntrospector().inspect(database, "renamed")
    sql = (
        "SELECT SUM(s.score) FROM teams t JOIN scores s ON s.team=t.id JOIN awards a ON a.team=t.id"
    )
    assessment = assess_clauses("Sum scores for teams with awards", sql, catalog)
    assert "SIBLING_JOIN_GRAIN_UNKNOWN" in {f.code for f in assessment.findings}
    assert not assessment.contradictions
    with sqlite3.connect(database) as db:
        assert db.execute(sql).fetchone()[0] == 60
        assert (
            db.execute(
                "SELECT SUM(score) FROM scores WHERE EXISTS "
                "(SELECT 1 FROM awards WHERE awards.team=scores.team)"
            ).fetchone()[0]
            == 20
        )
        # Equal-valued independent rows show why SUM(DISTINCT ...) is not a repair.
        assert db.execute(sql.replace("SUM(s.score)", "SUM(DISTINCT s.score)")).fetchone()[0] == 10


def test_model_findings_require_real_evidence_and_exact_span(database: Path) -> None:
    catalog = SQLiteIntrospector().inspect(database, "tiny")
    evidence = build_evidence("Count scores", catalog, None, "")
    findings = [
        ClauseFinding(
            code="hallucination",
            clause="WHERE",
            outcome=CheckOutcome.CONTRADICTION,
            message="error",
            evidence_ids=("gold",),
            question_span="Count",
        ),
        ClauseFinding(
            code="span",
            clause="WHERE",
            outcome=CheckOutcome.CONTRADICTION,
            message="error",
            evidence_ids=("question",),
            question_span="top",
        ),
    ]
    assert grounded_model_findings(ModelCritique(findings=findings), evidence, "Count scores") == ()


def test_actual_http_attempts_share_budget_across_roles_and_retries() -> None:
    calls = 0

    def respond(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"message": {"content": "invalid-json"}})

    settings = Settings(TEXT2SQL_OLLAMA_NUM_GPU=0, TEXT2SQL_GUARDED_RUN=True)
    client = httpx.Client(transport=httpx.MockTransport(respond), base_url="http://test")
    provider = OllamaProvider(settings, client=client, malformed_retries=5)
    budget = RequestBudget(max_requests=3)
    with request_scope(budget, "draft", 100), pytest.raises(BudgetExceededError):
        provider.generate_structured(prompt="test", response_model=SqlCandidate)
    assert calls == len(budget.attempts) == 3
    with request_scope(budget, "critic", 100), pytest.raises(BudgetExceededError):
        provider.generate_structured(prompt="test", response_model=ModelCritique)
    assert calls == 3


def test_native_sql_route_omits_json_and_forced_thinking_and_bounds_output() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "format" not in body and "think" not in body
        assert body["options"]["num_gpu"] == 0
        assert body["options"]["num_predict"] == 512
        assert body["keep_alive"] == 0
        return httpx.Response(200, json={"message": {"content": "```sql\nSELECT 1\n```"}})

    client = httpx.Client(transport=httpx.MockTransport(respond), base_url="http://test")
    provider = OllamaProvider(
        Settings(TEXT2SQL_OLLAMA_NUM_GPU=0, TEXT2SQL_GUARDED_RUN=True), client=client
    )
    with request_scope(RequestBudget(), "draft", 512):
        assert sql_text_candidate(provider.generate_sql_text(prompt="query")).sql == "SELECT 1"


def test_provider_refuses_unbounded_or_unguarded_generation_before_http() -> None:
    def respond(_: httpx.Request) -> httpx.Response:
        pytest.fail("Generation must be refused before HTTP")

    client = httpx.Client(transport=httpx.MockTransport(respond), base_url="http://test")
    for settings in (
        Settings(_env_file=None, TEXT2SQL_OLLAMA_NUM_GPU=None),
        Settings(TEXT2SQL_OLLAMA_NUM_GPU=0, TEXT2SQL_GUARDED_RUN=False),
    ):
        with pytest.raises(ConfigurationError):
            OllamaProvider(settings, client=client).generate_structured(
                prompt="query", response_model=SqlCandidate
            )


@pytest.mark.parametrize(
    "content", ["<think>SELECT 9", "```sql\nSELECT 1\n```\n```sql\nSELECT 2\n```", ""]
)
def test_native_adapter_rejects_incomplete_or_multiple_candidates(content: str) -> None:
    with pytest.raises(StructuredOutputError):
        sql_text_candidate(content)


def test_repair_cannot_change_untargeted_projection_or_population(database: Path) -> None:
    draft = SqlCandidate(sql="SELECT score FROM scores ORDER BY score ASC LIMIT 1", confidence=1)
    malicious = SqlCandidate(
        sql="SELECT id FROM scores WHERE id=1 ORDER BY id DESC LIMIT 1", confidence=1
    )
    result = run(
        database, QueueProvider([draft, ModelCritique(), malicious]), mode="repair", correction=True
    )
    assert result.result_rows == [[5]]
    assert not result.assessment["repair_admitted"]
    assert result.assessment["selection_reason"] == "draft_retained_repair_not_admitted"


def test_shadow_false_positive_on_valid_candidate_never_repairs(database: Path) -> None:
    # Fan-out risk routes critic even if DISTINCT legitimately counts the parent entity.
    sql = (
        "SELECT COUNT(DISTINCT t.id) FROM teams t JOIN scores s ON s.team=t.id "
        "JOIN awards a ON a.team=t.id"
    )
    false = ClauseFinding(
        code="invented",
        clause="SELECT",
        outcome=CheckOutcome.CONTRADICTION,
        message="Use count rows instead",
        evidence_ids=("question",),
        question_span="teams",
    )
    provider = QueueProvider(
        [SqlCandidate(sql=sql, confidence=0.8), ModelCritique(findings=[false])]
    )
    result = run(
        database,
        provider,
        mode="repair",
        correction=True,
        question="Count teams with scores and awards",
    )
    assert result.result_rows == [[1]]
    assert len(provider.prompts) == 2
    assert not result.assessment["repair_attempted"]
    assert result.assessment["semantic_status"] == "UNVERIFIED"


def test_evidence_overflow_is_grounding_error_without_generation(database: Path) -> None:
    provider = QueueProvider([])
    settings = Settings(TEXT2SQL_INPUT_TOKEN_BUDGET=256)
    service = A1QueryService(provider, settings)
    result = service.run(
        "Show scores " + "detail " * 200, database, SQLiteIntrospector().inspect(database, "tiny")
    )
    assert result.status is DirectStatus.GROUNDING_ERROR
    assert provider.prompts == []


def test_budget_exhaustion_in_shadow_keeps_valid_draft(database: Path) -> None:
    draft = SqlCandidate(sql="SELECT score FROM scores ORDER BY score ASC LIMIT 1", confidence=1)
    provider = QueueProvider([draft])
    settings = Settings(TEXT2SQL_CRITIC_MODE="repair", TEXT2SQL_A1_MAX_REQUESTS=1)
    result = A1QueryService(provider, settings, correction_enabled=True).run(
        "Show top 1 highest scores", database, SQLiteIntrospector().inspect(database, "tiny")
    )
    assert result.status is DirectStatus.SUCCEEDED
    assert result.result_rows == [[5]]
    assert result.assessment["actual_generation_requests"] == 1
    assert result.assessment["stage_errors"]["critic"]
    assert result.assessment["repair_skipped_reason"]


def test_rank_uses_outer_scope_and_scalar_equivalent_stays_unknown(database: Path) -> None:
    catalog = SQLiteIntrospector().inspect(database, "tiny")
    assert not assess_clauses(
        "Show top 1 highest scores", "SELECT MAX(score) FROM scores", catalog
    ).contradictions
    assert not assess_clauses(
        "Show 2 điểm cao nhất", "SELECT score FROM scores ORDER BY score DESC LIMIT 2", catalog
    ).contradictions


def test_shared_application_factory_routes_a1_and_persists_semantic_scope(
    database: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import yaml

    from agentic_text2sql.layer6_application import service_factory
    from agentic_text2sql.layer6_application.catalog_registry import CatalogRegistry
    from agentic_text2sql.layer6_application.run_store import SQLiteRunStore
    from agentic_text2sql.layer6_application.service import ApplicationQueryService

    root = Path(__file__).resolve().parents[2]
    digest = yaml.safe_load((root / "configs/models.yaml").read_text())["generator"]["digest"]
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "qwen3:14b-q4_K_M", "digest": digest}]}
            )
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "test-local-backend"})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"template": "test-native-template"})
        body = json.loads(request.content)
        assert "logical_plan" not in body["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": SqlCandidate(
                        sql="SELECT COUNT(*) FROM scores", confidence=0.5
                    ).model_dump_json()
                }
            },
        )

    settings = Settings(
        PROJECT_ROOT=root,
        TEXT2SQL_DATA_DIR=tmp_path / "data",
        TEXT2SQL_PIPELINE_MODE="a1",
        TEXT2SQL_OLLAMA_NUM_GPU=0,
        TEXT2SQL_GUARDED_RUN=True,
    )
    with httpx.Client(transport=httpx.MockTransport(respond), base_url="http://test") as client:
        monkeypatch.setattr(
            service_factory, "OllamaProvider", lambda config: OllamaProvider(config, client=client)
        )
        state = tmp_path / "application.sqlite"
        registry, runs = CatalogRegistry(state), SQLiteRunStore(state)
        registry.register("tiny", database)
        service = ApplicationQueryService(settings, registry, runs, service_factory.runtime_bundle)
        record = service.run("tiny", "How many scores?")
    assert calls == ["/api/tags", "/api/version", "/api/show", "/api/chat"]
    assert record.result is not None
    assert record.result["assessment"]["semantic_status"] == "UNVERIFIED"
    assert record.config["pipeline_mode"] == "a1"
    assert runs.events(record.run_id)[1].event == "ROUTED"
    assert runs.events(record.run_id)[4].details["semantic_status"] == "UNVERIFIED"
