from pathlib import Path
from typing import Any, Literal, cast

import pytest
from pydantic import BaseModel

from agentic_text2sql.contracts.planning import (
    AdaptiveRoute,
    ClausePlan,
    ComplexityDecision,
    ComplexityKind,
    DINSQLDraft,
    JoinStep,
    LogicalPlan,
    PlanningStrategy,
    SemanticLink,
    SemanticLinkPlan,
    SemanticRole,
)
from agentic_text2sql.contracts.retrieval import SchemaContext
from agentic_text2sql.contracts.semantics import (
    AggregateOperator,
    AggregateSpec,
    BindingStatus,
    SemanticBinding,
)
from agentic_text2sql.contracts.sql import DirectRunResult, DirectStatus, SqlCandidate
from agentic_text2sql.exceptions import StructuredOutputError
from agentic_text2sql.layer1_reasoning.decomposer import Decomposer
from agentic_text2sql.layer1_reasoning.planner import (
    BASELINE_PLANNER_PROMPT_VERSION,
    PlannerAgent,
)
from agentic_text2sql.layer1_reasoning.router import QueryRouter
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer2_grounding.service import GroundingService
from agentic_text2sql.layer3_generation.easy_compiler import GroundedEasyCompiler
from agentic_text2sql.layer3_generation.generator import GeneratorAgent
from agentic_text2sql.layer3_generation.normalizer import CandidateNormalizer
from agentic_text2sql.layer3_generation.prompt_builder import (
    BASELINE_GENERATOR_PROMPT_VERSION,
    GENERATOR_PROMPT_VERSION,
    PromptBuilder,
)
from agentic_text2sql.layer3_generation.service import GenerationService
from agentic_text2sql.layer4_validation.executor import ReadOnlySQLiteExecutor
from agentic_text2sql.layer4_validation.policy import SQLSafetyPolicy
from agentic_text2sql.layer6_application.query_service import DirectBaselineService

ROOT = Path(__file__).resolve().parents[2]
DATABASE = ROOT / "data/samples/synthetic_commerce_tiny.sqlite"


class QueueProvider:
    def __init__(self, responses: list[BaseModel | Exception]) -> None:
        self.responses = responses
        self.calls = 0

    def generate_structured(
        self, *, prompt: str, response_model: type[BaseModel], model: str | None = None
    ) -> Any:
        del prompt, response_model, model
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


class CorrectionMustNotRun:
    class CorrectorMetadata:
        prompt_version = "forbidden-corrector"

    class ValidationMustNotRun:
        def run(self, *_: object, **__: object) -> None:
            raise AssertionError("deterministic proof SQL must not enter model correction")

    corrector = CorrectorMetadata()
    validation = ValidationMustNotRun()

    def run(self, *_: object, **__: object) -> None:
        raise AssertionError("deterministic proof SQL must not enter model correction")


def plan() -> LogicalPlan:
    return LogicalPlan(
        question_language="en",
        task_type="aggregation",
        metrics=["order count"],
        required_concepts=["orders"],
    )


def service(provider: QueueProvider) -> DirectBaselineService:
    return DirectBaselineService(
        router=QueryRouter(),
        decomposer=Decomposer(),
        planner=PlannerAgent(provider, ROOT / "configs/prompts/planner_v2.j2"),
        generation=GenerationService(
            PromptBuilder(
                ROOT / "configs/prompts/generator_v4_cross_domain.j2",
                ROOT / "datasets/olist/business_glossary.yaml",
            ),
            GeneratorAgent(provider),
            CandidateNormalizer(),
            "fake-local",
        ),
        policy=SQLSafetyPolicy(),
        executor=ReadOnlySQLiteExecutor(),
    )


def run(provider: QueueProvider, question: str = "How many orders?") -> DirectRunResult:
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")
    return service(provider).run(question, DATABASE, catalog)


def test_direct_vertical_slice_succeeds_with_two_model_calls() -> None:
    provider = QueueProvider(
        [plan(), SqlCandidate(sql="SELECT COUNT(*) FROM orders", confidence=1)]
    )
    result = run(provider)
    assert result.status is DirectStatus.SUCCEEDED
    assert result.result_rows == [[4]]
    assert result.candidate is not None
    assert result.candidate.model_name == "fake-local"
    assert provider.calls == 2
    assert result.latency_ms["total"] >= 0


def test_malformed_planner_is_typed_model_error_not_crash() -> None:
    provider = QueueProvider([StructuredOutputError("malformed structured output")])
    result = run(provider)
    assert result.status is DirectStatus.MODEL_ERROR
    assert result.safe_message == "malformed structured output"
    assert "total" in result.latency_ms


def test_invalid_sql_is_typed_and_never_executes() -> None:
    provider = QueueProvider([plan(), SqlCandidate(sql="not sql", confidence=0.1)])
    result = run(provider)
    assert result.status is DirectStatus.INVALID_SQL
    assert "total" in result.latency_ms


def test_write_and_returns_stop_before_model() -> None:
    provider = QueueProvider([])
    write = run(provider, "Delete every order")
    returns = run(provider, "What is the return rate?")
    assert write.status is DirectStatus.WRITE_BLOCKED
    assert returns.status is DirectStatus.CLARIFY
    assert provider.calls == 0
    assert "total" in write.latency_ms and "total" in returns.latency_ms


class StubGrounding:
    def __init__(self, catalog_hash: str, *, proven: bool = False) -> None:
        self.prepare_calls = 0
        self.ground_calls = 0
        self.context = SchemaContext(
            db_id="synthetic",
            selected_tables=["orders"],
            selected_columns=["orders.order_id"],
            joins=[],
            evidence=[],
            catalog_hash=catalog_hash,
            rendered_context="TABLE orders(order_id TEXT)",
            estimated_tokens=10,
        )
        binding = (
            SemanticBinding(
                db_id="synthetic",
                catalog_hash=catalog_hash,
                status=BindingStatus.PROVEN,
                aggregate=AggregateSpec(
                    operator=AggregateOperator.COUNT_ROWS,
                    table="orders",
                    evidence_id="semantic.entity.orders",
                ),
                required_tables=("orders",),
                rule_ids=("entity.orders",),
            )
            if proven
            else None
        )
        self.links = SemanticLinkPlan(
            db_id="synthetic",
            catalog_hash=catalog_hash,
            links=(
                SemanticLink(
                    mention="orders",
                    role=SemanticRole.ENTITY,
                    table="orders",
                    evidence_id="synthetic.orders",
                    score=1,
                ),
            ),
            required_tables=("orders",),
            binding=binding,
        )

    def prepare_for_planning(self, question: str, decomposition: object) -> tuple[Any, Any]:
        del question, decomposition
        self.prepare_calls += 1
        return self.context, self.links

    def ground(self, question: str, plan: object) -> SchemaContext:
        del question, plan
        self.ground_calls += 1
        return self.context


class ComplexStubGrounding:
    def __init__(self, catalog_hash: str) -> None:
        self.prepare_calls = 0
        self.ground_calls = 0
        self.context = SchemaContext(
            db_id="synthetic",
            selected_tables=["order_items", "products"],
            selected_columns=[
                "order_items.price",
                "order_items.product_id",
                "products.category",
                "products.product_id",
            ],
            joins=["order_items.product_id = products.product_id"],
            evidence=[],
            catalog_hash=catalog_hash,
            rendered_context=(
                "TABLE order_items(product_id TEXT, price REAL)\n"
                "TABLE products(product_id TEXT, category TEXT)\n"
                "FK order_items.product_id = products.product_id"
            ),
            estimated_tokens=40,
        )
        self.links = SemanticLinkPlan(
            db_id="synthetic",
            catalog_hash=catalog_hash,
            links=(
                SemanticLink(
                    mention="revenue",
                    role=SemanticRole.METRIC,
                    table="order_items",
                    column="price",
                    evidence_id="synthetic.order_items.price",
                    score=1,
                ),
                SemanticLink(
                    mention="category",
                    role=SemanticRole.DIMENSION,
                    table="products",
                    column="category",
                    evidence_id="synthetic.products.category",
                    score=1,
                ),
            ),
            required_tables=("order_items", "products"),
            join_paths=("order_items.product_id = products.product_id",),
        )

    def prepare_for_planning(self, question: str, decomposition: object) -> tuple[Any, Any]:
        del question, decomposition
        self.prepare_calls += 1
        return self.context, self.links

    def ground(self, question: str, plan: object) -> SchemaContext:
        del question, plan
        self.ground_calls += 1
        return self.context


class FailingSpecialistGrounding(ComplexStubGrounding):
    def prepare_for_planning(self, question: str, decomposition: object) -> tuple[Any, Any]:
        del question, decomposition
        self.prepare_calls += 1
        raise ValueError("specialist retrieval evidence is inconsistent")


def grounded_service(
    provider: QueueProvider,
    catalog_hash: str,
    planning_mode: Literal["baseline", "hybrid", "din_sql"] = "din_sql",
    correction: object | None = None,
) -> DirectBaselineService:
    normalizer = CandidateNormalizer()
    baseline_generation = GenerationService(
        PromptBuilder(
            ROOT / "configs/prompts/generator_v4_cross_domain.j2",
            ROOT / "datasets/olist/business_glossary.yaml",
        ),
        GeneratorAgent(provider),
        normalizer,
        "fake-local",
        BASELINE_GENERATOR_PROMPT_VERSION,
    )
    din_generation = GenerationService(
        PromptBuilder(
            ROOT / "configs/prompts/generator_v5_din_sql.j2",
            ROOT / "datasets/olist/business_glossary.yaml",
        ),
        GeneratorAgent(provider),
        normalizer,
        "fake-local",
        GENERATOR_PROMPT_VERSION,
    )
    return DirectBaselineService(
        router=QueryRouter(),
        decomposer=Decomposer(),
        planner=PlannerAgent(
            provider,
            ROOT / "configs/prompts/planner_v2.j2",
            ROOT / "configs/prompts/planner_v3_din_sql.j2",
        ),
        generation=din_generation if planning_mode == "din_sql" else baseline_generation,
        din_generation=din_generation if planning_mode == "hybrid" else None,
        policy=SQLSafetyPolicy(),
        executor=ReadOnlySQLiteExecutor(),
        easy_compiler=GroundedEasyCompiler(normalizer),
        grounding=cast(
            GroundingService,
            StubGrounding(catalog_hash, proven=planning_mode == "hybrid"),
        ),
        correction=cast(Any, correction),
        din_correction=cast(Any, correction),
        planning_mode=planning_mode,
    )


def test_din_sql_handoff_uses_one_model_call_and_records_plan_validation() -> None:
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")
    provider = QueueProvider([SqlCandidate(sql="SELECT COUNT(*) FROM orders", confidence=1)])
    result = grounded_service(provider, catalog.catalog_hash).run(
        "How many orders?", DATABASE, catalog
    )
    assert result.status is DirectStatus.SUCCEEDED
    assert result.result_rows == [[4]]
    assert result.plan is not None and result.plan["complexity"]["strategy"] == "EASY"
    assert result.plan_validation == {
        "accepted": True,
        "signals": ["UNPROVEN_SEMANTIC_BINDING"],
        "blocking_signals": [],
        "advisory_signals": ["UNPROVEN_SEMANTIC_BINDING"],
        "safe_message": None,
    }
    assert provider.calls == 1


def test_hybrid_easy_route_replays_the_frozen_baseline_pipeline() -> None:
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")
    baseline_plan = LogicalPlan(
        question_language="en",
        task_type="aggregation",
        metrics=["order count"],
    )
    provider = QueueProvider(
        [baseline_plan, SqlCandidate(sql="SELECT COUNT(*) FROM orders", confidence=1)]
    )
    runtime = grounded_service(provider, catalog.catalog_hash, "hybrid")
    result = runtime.run("How many orders?", DATABASE, catalog)
    assert result.status is DirectStatus.SUCCEEDED
    assert result.candidate is not None
    assert result.candidate.prompt_version == BASELINE_GENERATOR_PROMPT_VERSION
    assert result.candidate.model_name == "fake-local"
    assert result.prompt_versions["planner"] == BASELINE_PLANNER_PROMPT_VERSION
    assert result.adaptive_route is not None
    assert result.adaptive_route["route"] == AdaptiveRoute.BASELINE_PRESERVE
    assert result.plan is not None and "complexity" not in result.plan
    assert result.plan_validation is None
    assert provider.calls == 2
    assert "planning" in result.latency_ms
    grounding = cast(StubGrounding, runtime.grounding)
    assert grounding.prepare_calls == 0
    assert grounding.ground_calls == 1


def test_hybrid_challenger_reuses_incumbent_plan_without_second_planner_call() -> None:
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")
    baseline_plan = LogicalPlan(
        question_language="en",
        task_type="aggregation",
        metrics=["order count"],
    )
    provider = QueueProvider([SqlCandidate(sql="SELECT COUNT(*) FROM orders", confidence=1)])
    runtime = grounded_service(provider, catalog.catalog_hash, "hybrid")

    result = runtime.run_from_baseline_plan("How many orders?", DATABASE, catalog, baseline_plan)

    assert result.status is DirectStatus.SUCCEEDED
    assert provider.calls == 0
    assert result.prompt_versions["control_plan_source"] == "incumbent_p6"
    assert result.adaptive_route is not None
    assert result.adaptive_route["route"] == AdaptiveRoute.DIN_SQL_ENHANCE


def test_hybrid_proof_compiler_is_not_rewritten_by_model_correction() -> None:
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")
    baseline_plan = LogicalPlan(
        question_language="en",
        task_type="aggregation",
        metrics=["order count"],
    )
    provider = QueueProvider([])
    runtime = grounded_service(
        provider,
        catalog.catalog_hash,
        "hybrid",
        correction=CorrectionMustNotRun(),
    )

    result = runtime.run_from_baseline_plan("How many orders?", DATABASE, catalog, baseline_plan)

    assert result.status is DirectStatus.SUCCEEDED
    assert result.result_rows == [[4]]
    assert result.candidate is not None
    assert result.candidate.model_name == "deterministic-grounded-compiler"
    assert provider.calls == 0


def test_hybrid_complex_route_adds_bounded_din_planning_and_generation() -> None:
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")
    baseline_plan = LogicalPlan(
        question_language="en",
        task_type="ranking",
        metrics=["item revenue"],
        dimensions=["product category"],
        sort=["revenue descending"],
        limit=5,
    )
    din_plan = DINSQLDraft(
        question_language="en",
        task_type="ranking",
        metrics=["item revenue"],
        dimensions=["product category"],
        sort=["revenue descending"],
        limit=5,
        complexity=ComplexityDecision(
            kind=ComplexityKind.MULTI_JOIN,
            strategy=PlanningStrategy.NON_NESTED,
        ),
        clauses=ClausePlan(
            select=["products.category", "SUM order_items.price"],
            from_tables=["order_items", "products"],
            joins=[
                JoinStep(
                    left_table="order_items",
                    right_table="products",
                    condition="order_items.product_id = products.product_id",
                    purpose="attach product category to each order item",
                )
            ],
            group_by=["products.category"],
            order_by=["item revenue descending"],
            limit=5,
            output_grain="one row per product category",
        ),
    )
    candidate = SqlCandidate(
        sql=(
            "SELECT products.category, SUM(order_items.price) AS revenue "
            "FROM order_items JOIN products "
            "ON order_items.product_id = products.product_id "
            "GROUP BY products.category ORDER BY revenue DESC LIMIT 5"
        ),
        confidence=1,
    )
    provider = QueueProvider([baseline_plan, din_plan, candidate])
    runtime = grounded_service(provider, catalog.catalog_hash, "hybrid")
    complex_grounding = ComplexStubGrounding(catalog.catalog_hash)
    runtime.grounding = cast(GroundingService, complex_grounding)
    result = runtime.run(
        "Top 5 product categories by item revenue",
        DATABASE,
        catalog,
    )
    assert result.status is DirectStatus.SUCCEEDED
    assert result.adaptive_route is not None
    assert result.adaptive_route["route"] == AdaptiveRoute.DIN_SQL_ENHANCE
    assert result.plan is not None
    assert result.plan["complexity"]["strategy"] == PlanningStrategy.NON_NESTED
    assert result.plan_validation is not None and result.plan_validation["accepted"]
    assert result.candidate is not None
    assert result.candidate.prompt_version == GENERATOR_PROMPT_VERSION
    assert provider.calls == 3
    assert complex_grounding.prepare_calls == 1
    assert complex_grounding.ground_calls == 0


def test_hybrid_din_planner_failure_backtracks_once_to_frozen_baseline() -> None:
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")
    baseline_plan = LogicalPlan(
        question_language="en",
        task_type="ranking",
        metrics=["item revenue"],
        dimensions=["product category"],
        sort=["revenue descending"],
        limit=5,
    )
    candidate = SqlCandidate(
        sql="SELECT COUNT(*) FROM orders",
        confidence=1,
    )
    provider = QueueProvider([baseline_plan, StructuredOutputError("invalid DIN plan"), candidate])
    runtime = grounded_service(provider, catalog.catalog_hash, "hybrid")
    complex_grounding = ComplexStubGrounding(catalog.catalog_hash)
    runtime.grounding = cast(GroundingService, complex_grounding)

    result = runtime.run(
        "Top 5 product categories by item revenue",
        DATABASE,
        catalog,
    )

    assert result.status is DirectStatus.SUCCEEDED
    assert result.result_rows == [[4]]
    assert result.adaptive_route is not None
    assert result.adaptive_route["route"] == AdaptiveRoute.BASELINE_PRESERVE
    assert "DIN_PLANNING_FAILED_BASELINE_FALLBACK" in result.adaptive_route["signals"]
    assert result.prompt_versions["planner"] == BASELINE_PLANNER_PROMPT_VERSION
    assert result.candidate is not None
    assert result.candidate.prompt_version == BASELINE_GENERATOR_PROMPT_VERSION
    assert provider.calls == 3
    assert complex_grounding.prepare_calls == 1
    assert complex_grounding.ground_calls == 1


def test_hybrid_din_grounding_failure_backtracks_once_to_frozen_baseline() -> None:
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")
    baseline_plan = LogicalPlan(
        question_language="en",
        task_type="ranking",
        metrics=["item revenue"],
        dimensions=["product category"],
        sort=["revenue descending"],
        limit=5,
    )
    provider = QueueProvider(
        [baseline_plan, SqlCandidate(sql="SELECT COUNT(*) FROM orders", confidence=1)]
    )
    runtime = grounded_service(provider, catalog.catalog_hash, "hybrid")
    failing_grounding = FailingSpecialistGrounding(catalog.catalog_hash)
    runtime.grounding = cast(GroundingService, failing_grounding)

    result = runtime.run("Top 5 product categories by item revenue", DATABASE, catalog)

    assert result.status is DirectStatus.SUCCEEDED
    assert result.result_rows == [[4]]
    assert result.adaptive_route is not None
    assert result.adaptive_route["route"] == AdaptiveRoute.BASELINE_PRESERVE
    assert "DIN_GROUNDING_FAILED_BASELINE_FALLBACK" in result.adaptive_route["signals"]
    assert result.candidate is not None
    assert result.candidate.prompt_version == BASELINE_GENERATOR_PROMPT_VERSION
    assert provider.calls == 2
    assert failing_grounding.prepare_calls == 1
    assert failing_grounding.ground_calls == 1


def test_hybrid_rejected_din_plan_backtracks_once_to_frozen_baseline() -> None:
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")
    baseline_plan = LogicalPlan(
        question_language="en",
        task_type="ranking",
        metrics=["item revenue"],
        dimensions=["product category"],
        sort=["revenue descending"],
        limit=5,
    )
    rejected_din_plan = DINSQLDraft(
        question_language="en",
        task_type="ranking",
        metrics=["item revenue"],
        dimensions=["product category"],
        sort=["revenue descending"],
        limit=5,
        complexity=ComplexityDecision(
            kind=ComplexityKind.SIMPLE,
            strategy=PlanningStrategy.EASY,
        ),
        clauses=ClausePlan(
            select=["invented_table.value"],
            from_tables=["invented_table"],
            order_by=["invented_table.value DESC"],
            limit=5,
            output_grain="one row per product category",
        ),
    )
    provider = QueueProvider(
        [
            baseline_plan,
            rejected_din_plan,
            SqlCandidate(sql="SELECT COUNT(*) FROM orders", confidence=1),
        ]
    )
    runtime = grounded_service(provider, catalog.catalog_hash, "hybrid")
    complex_grounding = ComplexStubGrounding(catalog.catalog_hash)
    runtime.grounding = cast(GroundingService, complex_grounding)

    result = runtime.run("Top 5 product categories by item revenue", DATABASE, catalog)

    assert result.status is DirectStatus.SUCCEEDED
    assert result.result_rows == [[4]]
    assert result.adaptive_route is not None
    assert result.adaptive_route["route"] == AdaptiveRoute.BASELINE_PRESERVE
    assert "DIN_PLAN_REJECTED_BASELINE_FALLBACK" in result.adaptive_route["signals"]
    assert result.plan is not None and "complexity" not in result.plan
    assert result.plan_validation is None
    assert result.candidate is not None
    assert result.candidate.prompt_version == BASELINE_GENERATOR_PROMPT_VERSION
    assert provider.calls == 3
    assert complex_grounding.prepare_calls == 1
    assert complex_grounding.ground_calls == 1


def test_din_sql_mode_refuses_to_start_without_grounding() -> None:
    provider = QueueProvider([])
    baseline = service(provider)
    with pytest.raises(ValueError, match="active grounded schema index"):
        DirectBaselineService(
            router=QueryRouter(),
            decomposer=Decomposer(),
            planner=PlannerAgent(provider, ROOT / "configs/prompts/planner_v2.j2"),
            generation=baseline.generation,
            policy=SQLSafetyPolicy(),
            executor=ReadOnlySQLiteExecutor(),
            planning_mode="din_sql",
        )
