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
    ComparisonOperator,
    EntityRule,
    JoinKind,
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
            "What is the average number of payment installments rounded to 4 decimals?",
            AggregateOperator.AVG,
            "olist_order_payments_dataset",
            "payment_installments",
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


def test_relational_proofs_generalize_beyond_observed_benchmark_wording() -> None:
    catalog, semantics = _fixtures()
    grouped_question = " ".join(
        (
            "Rank the top 3 English categories by total product price",
            "with an alphabetical tie-break.",
        )
    )
    grouped = resolve_semantic_binding(
        grouped_question,
        Decomposer().decompose(grouped_question),
        catalog,
        semantics,
    )
    comparison_question = (
        "Count orders where paid amount is greater than total product price at order grain."
    )
    comparison = resolve_semantic_binding(
        comparison_question,
        Decomposer().decompose(comparison_question),
        catalog,
        semantics,
    )
    intersection_question = (
        "How many records are present in both order item totals and order payment totals?"
    )
    intersection = resolve_semantic_binding(
        intersection_question,
        Decomposer().decompose(intersection_question),
        catalog,
        semantics,
    )

    assert grouped.status is BindingStatus.PROVEN
    assert grouped.grouped_aggregate is not None
    assert grouped.grouped_aggregate.limit == 3
    assert grouped.joins
    assert comparison.status is BindingStatus.PROVEN
    assert len(comparison.column_comparisons) == 1
    assert comparison.joins
    assert intersection.status is BindingStatus.PROVEN
    assert intersection.column_comparisons == ()
    assert intersection.joins


def test_per_entity_qualifier_is_proven_only_by_matching_source_grain() -> None:
    catalog, semantics = _fixtures()
    matching = "Report average shipping fee per order."
    mismatched = "Report average shipping fee per customer."

    order_binding = resolve_semantic_binding(
        matching,
        Decomposer().decompose(matching),
        catalog,
        semantics,
    )
    customer_binding = resolve_semantic_binding(
        mismatched,
        Decomposer().decompose(mismatched),
        catalog,
        semantics,
    )

    assert order_binding.status is BindingStatus.PROVEN
    assert order_binding.aggregate is not None
    assert order_binding.aggregate.table == "order_item_totals"
    assert order_binding.aggregate.operator is AggregateOperator.AVG
    assert customer_binding.status is BindingStatus.INCOMPLETE
    assert "NON_SCALAR_SHAPE" in customer_binding.reasons


def test_frequency_ranking_is_inferred_from_unique_entity_dimension_shape() -> None:
    catalog, semantics = _fixtures()
    question = "Return top 1 payment method by record frequency."
    binding = resolve_semantic_binding(
        question,
        Decomposer().decompose(question),
        catalog,
        semantics,
    )

    assert binding.status is BindingStatus.PROVEN
    assert binding.frequency_ranking is not None
    assert binding.frequency_ranking.table == "olist_order_payments_dataset"
    assert binding.frequency_ranking.dimension_column == "payment_type"
    assert binding.frequency_ranking.limit == 1


def test_catalog_frequency_ranking_supports_bounded_payment_type_rows() -> None:
    catalog, semantics = _fixtures()
    question = (
        "Trả về 5 payment type và số dòng tương ứng, sắp theo số dòng giảm dần rồi tên tăng dần."
    )
    binding = resolve_semantic_binding(
        question,
        Decomposer().decompose(question),
        catalog,
        semantics,
    )

    assert binding.status is BindingStatus.PROVEN
    assert binding.frequency_ranking is not None
    assert binding.frequency_ranking.table == "olist_order_payments_dataset"
    assert binding.frequency_ranking.dimension_column == "payment_type"
    assert binding.frequency_ranking.limit == 5


@pytest.mark.parametrize(
    ("question", "missing_table"),
    [
        ("Có bao nhiêu order không có payment total?", "order_payment_totals"),
        ("How many orders do not have an item total row?", "order_item_totals"),
        ("How many orders are without payment totals?", "order_payment_totals"),
    ],
)
def test_missing_one_to_one_child_resolves_typed_anti_join(
    question: str,
    missing_table: str,
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
    assert binding.aggregate.operator is AggregateOperator.COUNT_ROWS
    assert binding.aggregate.table == "olist_orders_dataset"
    assert len(binding.joins) == 1
    assert binding.joins[0].kind is JoinKind.LEFT
    assert binding.joins[0].right.table == missing_table
    assert len(binding.predicates) == 1
    assert binding.predicates[0].table == missing_table
    assert binding.predicates[0].operator is ComparisonOperator.IS_NULL


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


@pytest.mark.parametrize(
    ("question", "table", "column", "operator", "value"),
    [
        (
            "How many products have a missing category?",
            "olist_products_dataset",
            "product_category_name",
            ComparisonOperator.IS_NULL,
            None,
        ),
        (
            "How many review rows have a review score of exactly one?",
            "olist_order_reviews_dataset",
            "review_score",
            ComparisonOperator.EQ,
            1,
        ),
        (
            "Có bao nhiêu dòng review có điểm đánh giá bằng đúng năm?",
            "olist_order_reviews_dataset",
            "review_score",
            ComparisonOperator.EQ,
            5,
        ),
    ],
)
def test_catalog_predicate_rules_resolve_generic_null_and_numeric_equality(
    question: str,
    table: str,
    column: str,
    operator: ComparisonOperator,
    value: object,
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
    assert binding.aggregate.table == table
    assert len(binding.predicates) == 1
    assert (
        binding.predicates[0].table,
        binding.predicates[0].column,
        binding.predicates[0].operator,
        binding.predicates[0].value,
    ) == (table, column, operator, value)


def test_catalog_numeric_predicate_fails_closed_outside_declared_domain() -> None:
    catalog, semantics = _fixtures()
    question = "How many review rows have a review score of exactly nine?"
    binding = resolve_semantic_binding(
        question,
        Decomposer().decompose(question),
        catalog,
        semantics,
    )

    assert binding.status is BindingStatus.INCOMPLETE
    assert "PREDICATE_VALUE_OUT_OF_RANGE:review_score_equality" in binding.reasons


def test_non_null_predicate_composes_with_same_owner_status_filter() -> None:
    catalog, semantics = _fixtures()
    question = "How many delivered orders have a non-null delivery timestamp?"
    binding = resolve_semantic_binding(
        question,
        Decomposer().decompose(question),
        catalog,
        semantics,
    )

    assert binding.status is BindingStatus.PROVEN
    actual = [
        (predicate.column, predicate.operator, predicate.value) for predicate in binding.predicates
    ]
    assert actual == [
        ("order_status", ComparisonOperator.EQ, "delivered"),
        ("order_delivered_customer_date", ComparisonOperator.IS_NOT_NULL, None),
    ]


@pytest.mark.parametrize(
    ("question", "operator", "table", "column", "predicate_column"),
    [
        (
            "How many orders were delivered late based on actual versus estimated timestamp?",
            AggregateOperator.COUNT_ROWS,
            "order_delivery_facts",
            None,
            "is_late_delivered",
        ),
        (
            "Có bao nhiêu đơn dùng nhiều hơn một loại phương thức thanh toán riêng biệt?",
            AggregateOperator.COUNT_ROWS,
            "order_payment_totals",
            None,
            "distinct_payment_type_count",
        ),
        (
            "Với các đơn giao trễ, số ngày trễ trung bình là bao nhiêu, làm tròn 4 chữ số?",
            AggregateOperator.AVG,
            "order_delivery_facts",
            "delay_days",
            "is_late_delivered",
        ),
    ],
)
def test_derived_populations_compose_with_requested_metric_without_count_override(
    question: str,
    operator: AggregateOperator,
    table: str,
    column: str | None,
    predicate_column: str,
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
    assert (binding.aggregate.operator, binding.aggregate.table, binding.aggregate.column) == (
        operator,
        table,
        column,
    )
    assert [predicate.column for predicate in binding.predicates] == [predicate_column]


@pytest.mark.parametrize(
    ("question", "table", "column"),
    [
        ("Có bao nhiêu bang khách hàng khác nhau?", "olist_customers_dataset", "customer_state"),
        ("How many distinct seller states exist?", "olist_sellers_dataset", "seller_state"),
        (
            "How many distinct payment types occur in the payment rows?",
            "olist_order_payments_dataset",
            "payment_type",
        ),
        ("Có bao nhiêu city khách hàng khác nhau?", "olist_customers_dataset", "customer_city"),
    ],
)
def test_count_distinct_resolves_unique_entity_owned_dimension(
    question: str,
    table: str,
    column: str,
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
    assert binding.aggregate.operator is AggregateOperator.COUNT_DISTINCT
    assert (binding.aggregate.table, binding.aggregate.column) == (table, column)
    assert any(rule_id.startswith("schema.dimension.") for rule_id in binding.rule_ids)


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
        (
            "What is the maximum number of installments in any payment?",
            BindingStatus.INCOMPLETE,
            "AGGREGATE_UNRESOLVED",
        ),
        (
            "How many products have more than one photo?",
            BindingStatus.INCOMPLETE,
            "ORDERED_COMPARISON_UNRESOLVED",
        ),
        (
            "How many orders have a non-null unknown timestamp?",
            BindingStatus.INCOMPLETE,
            "NOT_NULL_PREDICATE_UNRESOLVED",
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
