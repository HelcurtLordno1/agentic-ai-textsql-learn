from pathlib import Path

from agentic_text2sql.contracts.planning import (
    ClausePlan,
    ComplexityDecision,
    ComplexityKind,
    DINSQLPlan,
    PlanningStrategy,
    SemanticLinkPlan,
)
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer3_generation.easy_compiler import GroundedEasyCompiler
from agentic_text2sql.layer3_generation.normalizer import CandidateNormalizer

ROOT = Path(__file__).resolve().parents[3]
DATABASE = ROOT / "data/processed/olist.sqlite"


def _plan(*, select: str, table: str, where: list[str] | None = None) -> DINSQLPlan:
    catalog = SQLiteIntrospector().inspect(DATABASE, "olist")
    return DINSQLPlan(
        question_language="en",
        task_type="aggregation",
        metrics=["fixture"],
        semantic_links=SemanticLinkPlan(
            db_id="olist",
            catalog_hash=catalog.catalog_hash,
            required_tables=(table,),
        ),
        complexity=ComplexityDecision(
            kind=ComplexityKind.AGGREGATE,
            strategy=PlanningStrategy.EASY,
            signals=("single_relation_aggregate",),
        ),
        clauses=ClausePlan(
            select=[select],
            from_tables=[table],
            where=where or [],
            output_grain="one scalar row",
        ),
    )


def _compile(plan: DINSQLPlan) -> str | None:
    catalog = SQLiteIntrospector().inspect(DATABASE, "olist")
    candidate = GroundedEasyCompiler(CandidateNormalizer()).compile(plan, catalog)
    return candidate.normalized_sql if candidate is not None else None


def test_compiles_catalog_checked_count_with_status_predicate() -> None:
    sql = _compile(
        _plan(
            select="COUNT rows of olist_orders_dataset",
            table="olist_orders_dataset",
            where=["olist_orders_dataset.order_status = 'delivered'"],
        )
    )
    assert sql == "SELECT COUNT(*) FROM olist_orders_dataset WHERE order_status = 'delivered'"


def test_compiles_sum_and_distinct_count() -> None:
    assert (
        _compile(
            _plan(
                select="SUM order_item_totals.product_revenue_cents",
                table="order_item_totals",
            )
        )
        == "SELECT SUM(product_revenue_cents) FROM order_item_totals"
    )
    assert (
        _compile(
            _plan(
                select="COUNT DISTINCT olist_customers_dataset.customer_unique_id",
                table="olist_customers_dataset",
            )
        )
        == "SELECT COUNT(DISTINCT customer_unique_id) FROM olist_customers_dataset"
    )


def test_refuses_unknown_identifier_and_non_scalar_shape() -> None:
    unknown = _plan(
        select="SUM order_item_totals.invented_revenue",
        table="order_item_totals",
    )
    assert _compile(unknown) is None
    grouped = unknown.model_copy(
        update={
            "clauses": unknown.clauses.model_copy(
                update={
                    "select": ["SUM order_item_totals.product_revenue_cents"],
                    "group_by": ["x"],
                }
            )
        }
    )
    assert _compile(grouped) is None
