from pathlib import Path

from agentic_text2sql.contracts.planning import (
    DecomposedQuestion,
    SemanticLink,
    SemanticLinkPlan,
    SemanticRole,
)
from agentic_text2sql.contracts.retrieval import (
    CatalogDocument,
    EvidenceItem,
    RankedDocument,
    RetrievalResult,
    SchemaContext,
)
from agentic_text2sql.layer1_reasoning.decomposer import Decomposer
from agentic_text2sql.layer1_reasoning.planner import PlannerAgent
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer2_grounding.semantic_links import build_semantic_link_plan

ROOT = Path(__file__).resolve().parents[3]
DATABASE = ROOT / "data/processed/olist.sqlite"


class UnusedProvider:
    def generate_structured(self, **_: object) -> None:
        raise AssertionError("hybrid deterministic planning must not call the model")


def _context(
    *tables: str, columns: list[str] | None = None, joins: list[str] | None = None
) -> SchemaContext:
    catalog = SQLiteIntrospector().inspect(DATABASE, "olist")
    return SchemaContext(
        db_id="olist",
        selected_tables=list(tables),
        selected_columns=columns or [],
        joins=joins or [],
        evidence=[],
        catalog_hash=catalog.catalog_hash,
    )


def _planner() -> PlannerAgent:
    return PlannerAgent(UnusedProvider(), ROOT / "configs/prompts/planner_v2.j2")  # type: ignore[arg-type]


def test_delivered_value_prefers_status_column_over_delivery_timestamp() -> None:
    catalog = SQLiteIntrospector().inspect(DATABASE, "olist")
    documents = tuple(
        CatalogDocument(
            document_id=f"olist.olist_orders_dataset.{column}",
            db_id="olist",
            kind="column",
            table="olist_orders_dataset",
            column=column,
            description=description,
            catalog_hash=catalog.catalog_hash,
        )
        for column, description in (
            ("order_delivered_carrier_date", "delivered carrier date delivery timestamp"),
        )
    )
    retrieval = RetrievalResult(
        db_id="olist",
        mode="hybrid",
        candidates=tuple(
            RankedDocument(document=document, score=1, sources=("bm25",)) for document in documents
        ),
        estimated_tokens=20,
        catalog_hash=catalog.catalog_hash,
    )
    context = _context(
        "olist_orders_dataset",
        columns=[
            "olist_orders_dataset.order_delivered_carrier_date",
            "olist_orders_dataset.order_status",
        ],
    )
    context.evidence = [
        EvidenceItem(
            evidence_id="olist.olist_orders_dataset.order_status",
            kind="column",
            table="olist_orders_dataset",
            column="order_status",
            score=0.5,
        )
    ]
    decomposition = Decomposer().decompose("How many orders were delivered?")
    links = build_semantic_link_plan(
        "How many orders were delivered?", decomposition, retrieval, context, catalog
    )
    status = next(link for link in links.links if link.role is SemanticRole.FILTER)
    assert status.column == "order_status"
    assert status.value == "delivered"


def test_scalar_revenue_uses_metric_view_without_disconnected_product_join() -> None:
    context = _context(
        "olist_order_items_dataset",
        "olist_products_dataset",
        "order_item_totals",
        columns=["order_item_totals.product_revenue_cents"],
        joins=["olist_order_items_dataset.product_id = olist_products_dataset.product_id"],
    )
    links = SemanticLinkPlan(
        db_id="olist",
        catalog_hash=context.catalog_hash,
        links=(
            SemanticLink(
                mention="products",
                role=SemanticRole.ENTITY,
                table="olist_products_dataset",
                evidence_id="olist.olist_products_dataset",
                score=1,
                required=True,
            ),
            SemanticLink(
                mention="revenue",
                role=SemanticRole.METRIC,
                table="order_item_totals",
                column="product_revenue_cents",
                evidence_id="olist.order_item_totals.product_revenue_cents",
                score=1,
            ),
        ),
        required_tables=(),
        join_paths=tuple(context.joins),
    )
    question = "Tổng doanh thu sản phẩm tính theo cents là bao nhiêu?"
    plan = _planner().plan_grounded(question, Decomposer().decompose(question), links, context)
    assert plan.clauses.from_tables == ["order_item_totals"]
    assert plan.clauses.joins == []
    assert plan.clauses.select == ["SUM order_item_totals.product_revenue_cents"]


def test_unique_customer_count_is_scalar_distinct_without_orders_join() -> None:
    context = _context(
        "olist_customers_dataset",
        "olist_orders_dataset",
        columns=["olist_customers_dataset.customer_unique_id"],
        joins=["olist_orders_dataset.customer_id = olist_customers_dataset.customer_id"],
    )
    links = SemanticLinkPlan(
        db_id="olist",
        catalog_hash=context.catalog_hash,
        links=(
            SemanticLink(
                mention="customer",
                role=SemanticRole.DIMENSION,
                table="olist_customers_dataset",
                column="customer_unique_id",
                evidence_id="olist.olist_customers_dataset.customer_unique_id",
                score=1,
            ),
        ),
        population_owner="olist_customers_dataset",
        required_tables=("olist_customers_dataset",),
        join_paths=tuple(context.joins),
    )
    question = "Có bao nhiêu người mua duy nhất theo customer_unique_id?"
    decomposition = DecomposedQuestion(
        question_language="vi",
        metric_hints=["customers count"],
        entity_hints=["customers"],
        rationale="fixture",
    )
    plan = _planner().plan_grounded(question, decomposition, links, context)
    assert plan.clauses.from_tables == ["olist_customers_dataset"]
    assert plan.clauses.select == ["COUNT DISTINCT olist_customers_dataset.customer_unique_id"]
    assert plan.clauses.output_grain == "one scalar row"


def test_how_many_sellers_normalizes_to_scalar_entity_count() -> None:
    decomposition = Decomposer().decompose("How many sellers are in the marketplace?")
    assert decomposition.metric_hints == ["sellers count"]
    assert decomposition.dimension_hints == []
    context = _context("olist_sellers_dataset")
    links = SemanticLinkPlan(
        db_id="olist",
        catalog_hash=context.catalog_hash,
        population_owner="olist_sellers_dataset",
        required_tables=("olist_sellers_dataset",),
    )
    plan = _planner().plan_grounded(
        "How many sellers are in the marketplace?", decomposition, links, context
    )
    assert plan.task_type == "aggregation"
    assert plan.dimensions == []
    assert plan.clauses.select == ["COUNT rows of olist_sellers_dataset"]
    assert plan.clauses.output_grain == "one scalar row"
