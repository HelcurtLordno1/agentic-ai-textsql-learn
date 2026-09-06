from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agentic_text2sql.contracts.planning import (
    ClausePlan,
    ComplexityDecision,
    ComplexityKind,
    DINSQLDraft,
    DINSQLPlan,
    JoinStep,
    PlanningStrategy,
    SemanticLink,
    SemanticLinkPlan,
    SemanticRole,
    SubqueryStep,
)
from agentic_text2sql.contracts.retrieval import SchemaContext
from agentic_text2sql.layer1_reasoning.decomposer import Decomposer
from agentic_text2sql.layer1_reasoning.plan_validator import validate_plan
from agentic_text2sql.layer1_reasoning.planner import PlannerAgent
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector

ROOT = Path(__file__).resolve().parents[3]
DATABASE = ROOT / "data/samples/synthetic_commerce_tiny.sqlite"


class RecordingProvider:
    def __init__(self, response: BaseModel) -> None:
        self.response = response
        self.prompt = ""

    def generate_structured(
        self, *, prompt: str, response_model: type[BaseModel], model: str | None = None
    ) -> Any:
        del response_model, model
        self.prompt = prompt
        return self.response


def schema_context() -> SchemaContext:
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")
    return SchemaContext(
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
        catalog_hash=catalog.catalog_hash,
        rendered_context=(
            "TABLE order_items(product_id TEXT, price REAL)\n"
            "TABLE products(product_id TEXT, category TEXT)\n"
            "FK order_items.product_id = products.product_id"
        ),
        estimated_tokens=40,
    )


def semantic_links() -> SemanticLinkPlan:
    context = schema_context()
    return SemanticLinkPlan(
        db_id="synthetic",
        catalog_hash=context.catalog_hash,
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


def ranking_draft() -> DINSQLDraft:
    return DINSQLDraft(
        question_language="en",
        task_type="ranking",
        metrics=["revenue"],
        dimensions=["category"],
        sort=["metric descending", "dimension ascending tie-break"],
        limit=5,
        required_concepts=["revenue", "category"],
        complexity=ComplexityDecision(
            kind=ComplexityKind.SIMPLE,
            strategy=PlanningStrategy.EASY,
            signals=("model_guess",),
        ),
        clauses=ClausePlan(
            select=["products.category", "SUM(order_items.price) as revenue"],
            from_tables=["order_items", "products"],
            joins=[
                JoinStep(
                    left_table="order_items",
                    right_table="products",
                    condition="order_items.product_id = products.product_id",
                    purpose="attach the category to each item",
                )
            ],
            group_by=["products.category"],
            order_by=["revenue descending", "products.category ascending"],
            limit=5,
            output_grain="one row per category",
        ),
    )


def test_grounded_planner_uses_schema_links_and_normalizes_complexity() -> None:
    provider = RecordingProvider(ranking_draft())
    planner = PlannerAgent(
        provider,
        ROOT / "configs/prompts/planner_v2.j2",
        ROOT / "configs/prompts/planner_v3_din_sql.j2",
    )
    question = "Top 5 categories by revenue with alphabetical tie-break"
    plan = planner.plan_grounded(
        question,
        Decomposer().decompose(question),
        semantic_links(),
        schema_context(),
    )
    assert plan.complexity.kind is ComplexityKind.MULTI_JOIN
    assert plan.complexity.strategy is PlanningStrategy.NON_NESTED
    assert plan.semantic_links == semantic_links()
    assert provider.prompt == ""
    assert plan.clauses.from_tables == ["order_items", "products"]
    assert plan.clauses.joins[0].condition == "order_items.product_id = products.product_id"


def test_plan_validator_accepts_declared_fk_and_rejects_missing_owner() -> None:
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")
    valid = DINSQLPlan(
        **ranking_draft().model_dump(exclude={"complexity"}),
        semantic_links=semantic_links(),
        complexity=ComplexityDecision(
            kind=ComplexityKind.MULTI_JOIN,
            strategy=PlanningStrategy.NON_NESTED,
            signals=("multiple_tables_or_join",),
        ),
    )
    report = validate_plan(valid, catalog, schema_context())
    assert report.accepted

    broken_clauses = valid.clauses.model_copy(update={"from_tables": ["order_items"], "joins": []})
    broken = valid.model_copy(update={"clauses": broken_clauses})
    rejected = validate_plan(broken, catalog, schema_context())
    assert not rejected.accepted
    assert "SEMANTIC_OWNER_MISSING" in rejected.signals
    assert "COLUMN_OWNER_NOT_IN_FROM" in rejected.signals


def test_nested_dependencies_must_be_ordered() -> None:
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")
    draft = ranking_draft()
    clauses = draft.clauses.model_copy(
        update={
            "subqueries": [
                SubqueryStep(
                    step_id="outer_metric",
                    question="average the per-category totals",
                    output_grain="one scalar row",
                    select=["SUM(order_items.price)"],
                    from_tables=["order_items"],
                    depends_on=("category_totals",),
                )
            ]
        }
    )
    plan = DINSQLPlan(
        **draft.model_dump(exclude={"complexity", "clauses"}),
        semantic_links=semantic_links(),
        complexity=ComplexityDecision(
            kind=ComplexityKind.NESTED_SET_WINDOW,
            strategy=PlanningStrategy.NESTED,
            signals=("subquery_or_set_or_window",),
        ),
        clauses=clauses,
    )
    report = validate_plan(plan, catalog, schema_context())
    assert "SUBQUERY_DEPENDENCY_NOT_PRIOR" in report.signals
