from __future__ import annotations

from pathlib import Path

import pytest

from agentic_text2sql.contracts.retrieval import (
    CatalogDocument,
    RankedDocument,
    RetrievalResult,
)
from agentic_text2sql.contracts.semantics import (
    AggregateOperator,
    BindingStatus,
    EntityRule,
)
from agentic_text2sql.layer1_reasoning.decomposer import Decomposer
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer2_grounding.semantic_catalog import (
    load_semantic_catalog,
    resolve_semantic_binding,
    validate_semantic_catalog,
)
from agentic_text2sql.layer2_grounding.service import GroundingService

ROOT = Path(__file__).resolve().parents[3]
DATABASE = ROOT / "data/processed/olist.sqlite"
SEMANTICS = ROOT / "datasets/olist/semantic_catalog.yaml"


def _fixtures():  # type: ignore[no-untyped-def]
    catalog = SQLiteIntrospector().inspect(DATABASE, "olist")
    semantics = load_semantic_catalog(SEMANTICS, catalog)
    return catalog, semantics


@pytest.mark.parametrize(
    ("question", "operator", "table", "column", "predicate_value"),
    [
        (
            "Count all marketplace sellers",
            AggregateOperator.COUNT_ROWS,
            "olist_sellers_dataset",
            None,
            None,
        ),
        (
            "Số lượng người bán hiện có",
            AggregateOperator.COUNT_ROWS,
            "olist_sellers_dataset",
            None,
            None,
        ),
        (
            "What is total merchandise revenue?",
            AggregateOperator.SUM,
            "order_item_totals",
            "product_revenue_cents",
            None,
        ),
        (
            "Cho biết tổng doanh thu hàng hóa",
            AggregateOperator.SUM,
            "order_item_totals",
            "product_revenue_cents",
            None,
        ),
        (
            "What is the average merchandise revenue?",
            AggregateOperator.AVG,
            "order_item_totals",
            "product_revenue_cents",
            None,
        ),
        (
            "What is the average item count per order?",
            AggregateOperator.AVG,
            "order_item_totals",
            "item_count",
            None,
        ),
        (
            "Trung bình mỗi đơn có bao nhiêu item, làm tròn 4 chữ số?",
            AggregateOperator.AVG,
            "order_item_totals",
            "item_count",
            None,
        ),
        (
            "What is the average delivery time?",
            AggregateOperator.AVG,
            "order_delivery_facts",
            "delivery_days",
            None,
        ),
        (
            "What is the average review score rounded to 6 decimals?",
            AggregateOperator.AVG,
            "order_review_summary",
            "average_review_score",
            None,
        ),
        (
            "How many unique buyers exist using customer_unique_id?",
            AggregateOperator.COUNT_DISTINCT,
            "olist_customers_dataset",
            "customer_unique_id",
            None,
        ),
        (
            "Đếm đơn hàng đã hủy",
            AggregateOperator.COUNT_ROWS,
            "olist_orders_dataset",
            None,
            "canceled",
        ),
        (
            "How many repeat customers do we have?",
            AggregateOperator.COUNT_ROWS,
            "customer_order_facts",
            None,
            1,
        ),
        (
            "Đếm người mua lặp lại",
            AggregateOperator.COUNT_ROWS,
            "customer_order_facts",
            None,
            1,
        ),
        (
            "How many orders with multiple payment methods?",
            AggregateOperator.COUNT_ROWS,
            "order_payment_totals",
            None,
            1,
        ),
        (
            "How many late deliveries?",
            AggregateOperator.COUNT_ROWS,
            "order_delivery_facts",
            None,
            1,
        ),
        (
            "Số đơn hàng lớn nhất từng được ghi nhận cho một customer_unique_id là bao nhiêu?",
            AggregateOperator.MAX,
            "customer_order_facts",
            "order_count",
            None,
        ),
    ],
)
def test_paraphrase_distribution_resolves_typed_scalar_semantics(
    question: str,
    operator: AggregateOperator,
    table: str,
    column: str | None,
    predicate_value: str | int | None,
) -> None:
    catalog, semantics = _fixtures()
    binding = resolve_semantic_binding(
        question,
        Decomposer().decompose(question),
        catalog,
        semantics,
    )
    assert binding.status is BindingStatus.PROVEN
    assert binding.aggregate is not None
    assert (
        binding.aggregate.operator,
        binding.aggregate.table,
        binding.aggregate.column,
    ) == (operator, table, column)
    assert [predicate.value for predicate in binding.predicates] == (
        [] if predicate_value is None else [predicate_value]
    )
    if "review score" in question:
        assert binding.aggregate.source_grain == "one row per order_id"
        assert binding.aggregate.weight_column == "review_row_count"
        assert binding.aggregate.rounding_digits == 6


def test_filler_words_do_not_change_the_resolved_contract() -> None:
    catalog, semantics = _fixtures()
    variants = (
        "How many sellers?",
        "Please tell me how many sellers exist.",
        "Could you please tell me the number of sellers?",
    )
    bindings = [
        resolve_semantic_binding(
            question,
            Decomposer().decompose(question),
            catalog,
            semantics,
        )
        for question in variants
    ]
    assert all(binding.status is BindingStatus.PROVEN for binding in bindings)
    assert len({binding.aggregate for binding in bindings}) == 1
    assert len({binding.rule_ids for binding in bindings}) == 1


def test_review_frequency_resolves_raw_row_grain_contract() -> None:
    catalog, semantics = _fixtures()
    question = "Điểm review nào xuất hiện nhiều nhất? Trả về điểm và số review."
    binding = resolve_semantic_binding(
        question,
        Decomposer().decompose(question),
        catalog,
        semantics,
    )
    assert binding.status is BindingStatus.PROVEN
    assert binding.aggregate is None
    assert binding.frequency_ranking is not None
    assert binding.frequency_ranking.table == "olist_order_reviews_dataset"
    assert binding.frequency_ranking.dimension_column == "review_score"
    assert binding.frequency_ranking.limit == 1


def test_payment_frequency_resolves_a_typed_raw_row_ranking() -> None:
    catalog, semantics = _fixtures()
    question = "Which payment type has the most payment records? Return type and count."
    binding = resolve_semantic_binding(
        question, Decomposer().decompose(question), catalog, semantics
    )

    assert binding.status is BindingStatus.PROVEN
    assert binding.aggregate is None
    assert binding.frequency_ranking is not None
    assert binding.frequency_ranking.table == "olist_order_payments_dataset"
    assert binding.frequency_ranking.dimension_column == "payment_type"
    assert binding.frequency_ranking.limit == 1
    assert binding.required_columns == ("olist_order_payments_dataset.payment_type",)


def test_freight_per_order_resolves_catalog_grain_and_rounding() -> None:
    catalog, semantics = _fixtures()
    question = "What is the average freight amount per order in cents rounded to 2 decimals?"
    binding = resolve_semantic_binding(
        question, Decomposer().decompose(question), catalog, semantics
    )

    assert binding.status is BindingStatus.PROVEN
    assert binding.aggregate is not None
    assert binding.aggregate.operator is AggregateOperator.AVG
    assert binding.aggregate.table == "order_item_totals"
    assert binding.aggregate.column == "freight_cents"
    assert binding.aggregate.source_grain == "one row per order_id"
    assert binding.aggregate.rounding_digits == 2


@pytest.mark.parametrize(
    ("question", "status", "reason"),
    [
        ("Show orders by state", BindingStatus.INCOMPLETE, "NON_SCALAR_SHAPE"),
        (
            "How many sellers with an unknown status?",
            BindingStatus.INCOMPLETE,
            "QUALIFIER_UNRESOLVED",
        ),
        (
            "How many customers and sellers?",
            BindingStatus.AMBIGUOUS,
            "MULTIPLE_METRIC_OR_ENTITY_RULES",
        ),
        (
            "How many merchandise revenue records?",
            BindingStatus.INCOMPLETE,
            "COUNT_METRIC_CONFLICT",
        ),
    ],
)
def test_unproven_semantics_fail_closed(
    question: str,
    status: BindingStatus,
    reason: str,
) -> None:
    catalog, semantics = _fixtures()
    binding = resolve_semantic_binding(
        question,
        Decomposer().decompose(question),
        catalog,
        semantics,
    )
    assert binding.status is status
    assert reason in binding.reasons


def test_semantic_catalog_rejects_identifiers_absent_from_database() -> None:
    catalog, semantics = _fixtures()
    invalid = semantics.model_copy(
        update={
            "entities": {
                **semantics.entities,
                "invented": EntityRule(
                    aliases=("invented",),
                    table="missing_table",
                    row_grain="one row per invented entity",
                ),
            }
        }
    )
    with pytest.raises(ValueError, match="unknown table missing_table"):
        validate_semantic_catalog(invalid, catalog)


def test_grounding_service_carries_proven_binding_and_required_schema_evidence() -> None:
    catalog, semantics = _fixtures()
    documents = tuple(
        CatalogDocument(
            document_id=f"olist.olist_sellers_dataset.{column or 'table'}",
            db_id="olist",
            kind="column" if column is not None else "table",
            table="olist_sellers_dataset",
            column=column,
            description=f"seller semantic evidence {column or 'table'}",
            catalog_hash=catalog.catalog_hash,
        )
        for column in (None, "seller_id")
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

    class StubRetriever:
        def retrieve(self, *_: object, **__: object) -> RetrievalResult:
            return retrieval

    service = GroundingService(  # type: ignore[arg-type]
        StubRetriever(),
        catalog,
        mode="hybrid",
        semantic_catalog=semantics,
    )
    question = "Count all marketplace sellers"
    context, links = service.prepare_for_planning(question, Decomposer().decompose(question))
    assert context.selected_tables == ["olist_sellers_dataset"]
    assert links.binding is not None
    assert links.binding.status is BindingStatus.PROVEN
    assert links.binding.required_tables == ("olist_sellers_dataset",)


def test_semantic_proof_fast_path_never_calls_retriever() -> None:
    catalog, semantics = _fixtures()

    class ForbiddenRetriever:
        def retrieve(self, *_: object, **__: object) -> RetrievalResult:
            raise AssertionError("semantic proof must not invoke retrieval")

    service = GroundingService(  # type: ignore[arg-type]
        ForbiddenRetriever(),
        catalog,
        mode="hybrid",
        semantic_catalog=semantics,
    )
    question = "Count all marketplace sellers"
    prepared = service.prepare_semantic_proof(question, Decomposer().decompose(question))

    assert prepared is not None
    context, links = prepared
    assert context.selected_tables == ["olist_sellers_dataset"]
    assert context.selected_columns == []
    assert links.population_owner == "olist_sellers_dataset"
    assert links.binding is not None and links.binding.status is BindingStatus.PROVEN
