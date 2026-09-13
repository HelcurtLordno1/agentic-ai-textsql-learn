import sqlite3

from agentic_text2sql.contracts.planning import (
    ClausePlan,
    ComplexityDecision,
    ComplexityKind,
    DINSQLPlan,
    LogicalPlan,
    PlanningStrategy,
    SemanticLinkPlan,
)
from agentic_text2sql.contracts.semantics import (
    AggregateOperator,
    AggregateSpec,
    BindingStatus,
    ComparisonOperator,
    PredicateSpec,
    SemanticBinding,
)
from agentic_text2sql.contracts.validation import ErrorClass, ResultPreview
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer4_validation.result_validator import validate_result
from agentic_text2sql.layer4_validation.semantic_checks import validate_semantics
from agentic_text2sql.layer4_validation.service import ValidationService


def aggregate_plan(metric: str = "customer count") -> LogicalPlan:
    return LogicalPlan(
        question_language="vi",
        task_type="aggregation",
        metrics=[metric],
        required_concepts=[],
    )


def proven_derived_plan(rule_id: str, table: str, predicate: PredicateSpec) -> DINSQLPlan:
    aggregate = AggregateSpec(
        operator=AggregateOperator.COUNT_ROWS,
        table=table,
        evidence_id=f"semantic.{rule_id}",
    )
    binding = SemanticBinding(
        db_id="olist",
        catalog_hash="catalog",
        status=BindingStatus.PROVEN,
        aggregate=aggregate,
        predicates=(predicate,),
        required_tables=(table,),
        required_columns=(f"{table}.{predicate.column}",),
        rule_ids=(rule_id,),
    )
    return DINSQLPlan(
        question_language="en",
        task_type="aggregation",
        metrics=["count"],
        semantic_links=SemanticLinkPlan(
            db_id="olist",
            catalog_hash="catalog",
            binding=binding,
            required_tables=(table,),
        ),
        complexity=ComplexityDecision(
            kind=ComplexityKind.AGGREGATE,
            strategy=PlanningStrategy.EASY,
        ),
        clauses=ClausePlan(
            select=[f"COUNT rows of {table}"],
            from_tables=[table],
            where=[f"{table}.{predicate.column} predicate"],
            output_grain="one scalar row",
            aggregate=aggregate,
            predicates=[predicate],
        ),
    )


def test_scalar_aggregate_shape_is_checked_without_gold() -> None:
    report = validate_result(
        ResultPreview(columns=["customers", "orders"], rows=[[3, 7]]), aggregate_plan()
    )
    assert not report.accepted
    assert report.error_class is ErrorClass.RESULT_SHAPE_MISMATCH
    assert report.signals == ["SCALAR_AGGREGATE_COLUMN_COUNT"]
    assert report.repair_eligible


def test_average_intent_requires_average_aggregate() -> None:
    report = validate_semantics(
        "What is the average review score?",
        aggregate_plan("average review score"),
        "SELECT review_score FROM reviews",
    )
    assert not report.accepted
    assert "AVERAGE_AGGREGATE_MISSING" in report.signals


def test_late_delivery_rule_rejects_status_population_narrowing() -> None:
    report = validate_semantics(
        "Có bao nhiêu đơn giao trễ?",
        aggregate_plan("delivery"),
        "SELECT COUNT(*) FROM orders WHERE order_status = 'delivered' "
        "AND order_delivered_customer_date > order_estimated_delivery_date",
    )
    assert not report.accepted
    assert "DELIVERY_POPULATION_NARROWED_BY_STATUS" in report.signals


def test_late_delivery_does_not_require_delivered_status_filter() -> None:
    report = validate_semantics(
        "How many orders were delivered late based on actual versus estimated delivery timestamp?",
        aggregate_plan("late order count"),
        "SELECT COUNT(*) FROM olist_orders_dataset "
        "WHERE order_delivered_customer_date IS NOT NULL "
        "AND order_delivered_customer_date > order_estimated_delivery_date",
        db_id="olist",
    )
    assert report.accepted


def test_semantic_validator_trusts_proven_derived_grain_lineage() -> None:
    returning = proven_derived_plan(
        "derived.repeat_customer",
        "customer_order_facts",
        PredicateSpec(
            table="customer_order_facts",
            column="order_count",
            operator=ComparisonOperator.GT,
            value=1,
            evidence_id="semantic.derived.repeat_customer.order_count",
        ),
    )
    report = validate_semantics(
        "How many returning customers have more than one order?",
        returning,
        "SELECT COUNT(*) FROM customer_order_facts WHERE order_count > 1",
        db_id="olist",
    )
    assert report.accepted


def test_semantic_validator_keeps_lexical_guard_without_proven_lineage() -> None:
    report = validate_semantics(
        "How many returning customers have more than one order?",
        aggregate_plan("returning customer count"),
        "SELECT COUNT(*) FROM customer_order_facts WHERE order_count > 1",
        db_id="olist",
    )
    assert not report.accepted
    assert "CUSTOMER_IDENTITY_NOT_UNIQUE" in report.signals


def test_explicit_customer_identity_trusts_proven_source_grain() -> None:
    aggregate = AggregateSpec(
        operator=AggregateOperator.MAX,
        table="customer_order_facts",
        column="order_count",
        evidence_id="semantic.derived.customer_order_max",
        source_grain="one row per customer_unique_id",
    )
    binding = SemanticBinding(
        db_id="olist",
        catalog_hash="catalog",
        status=BindingStatus.PROVEN,
        aggregate=aggregate,
        required_tables=("customer_order_facts",),
        required_columns=("customer_order_facts.order_count",),
        rule_ids=("derived.customer_order_max",),
    )
    plan = DINSQLPlan(
        question_language="vi",
        task_type="aggregation",
        metrics=["order count"],
        semantic_links=SemanticLinkPlan(
            db_id="olist",
            catalog_hash="catalog",
            binding=binding,
            required_tables=("customer_order_facts",),
        ),
        complexity=ComplexityDecision(
            kind=ComplexityKind.AGGREGATE,
            strategy=PlanningStrategy.EASY,
        ),
        clauses=ClausePlan(
            select=["MAX customer_order_facts.order_count"],
            from_tables=["customer_order_facts"],
            output_grain="one scalar row",
            aggregate=aggregate,
        ),
    )
    report = validate_semantics(
        "Số đơn hàng lớn nhất từng được ghi nhận cho một customer_unique_id là bao nhiêu?",
        plan,
        "SELECT MAX(order_count) FROM customer_order_facts",
        db_id="olist",
    )
    assert report.accepted


def test_valid_scalar_aggregate_has_no_semantic_suspicion() -> None:
    result_report = validate_result(
        ResultPreview(columns=["average_review_score"], rows=[[4.1]]),
        aggregate_plan("average review score"),
    )
    semantic_report = validate_semantics(
        "What is the average review score?",
        aggregate_plan("average review score"),
        "SELECT AVG(review_score) FROM reviews",
    )
    assert result_report.accepted
    assert semantic_report.accepted


def test_ranking_requires_desc_exact_limit_and_tie_break() -> None:
    plan = LogicalPlan(
        question_language="en",
        task_type="aggregation",
        metrics=["count"],
        dimensions=["payment type"],
    )
    report = validate_semantics(
        "Which payment type has the most records? "
        "Return type and count with alphabetical tie-break.",
        plan,
        "SELECT payment_type, COUNT(*) c FROM payments GROUP BY payment_type ORDER BY payment_type",
    )
    assert not report.accepted
    assert set(report.signals) >= {
        "RANKING_PRIMARY_NOT_DESC",
        "RANKING_LIMIT_MISMATCH",
        "ALPHABETICAL_TIE_BREAK_MISSING",
    }


def test_high_precision_grain_and_business_rules() -> None:
    cases = (
        (
            "What is the average freight amount per order?",
            "SELECT AVG(freight_value_cents) FROM order_items",
            "FREIGHT_PER_ORDER_GRAIN_MISMATCH",
        ),
        (
            "Có bao nhiêu order có nhiều review row?",
            "SELECT COUNT(DISTINCT order_id) FROM reviews",
            "MULTIPLE_REVIEW_ROWS_RULE_MISSING",
        ),
        (
            "How many products have more than one photo?",
            "SELECT COUNT(*) FROM products",
            "PRODUCT_PHOTO_QUANTITY_FILTER_MISSING",
        ),
        (
            "Số đơn hàng lớn nhất từng được ghi nhận là bao nhiêu?",
            "SELECT customer_id, order_count FROM facts ORDER BY order_count DESC LIMIT 1",
            "SCALAR_MAXIMUM_AGGREGATE_MISSING",
        ),
    )
    for question, sql, signal in cases:
        report = validate_semantics(question, aggregate_plan("count"), sql)
        assert not report.accepted
        assert signal in report.signals


def test_record_count_rejects_distinct_and_month_keeps_year_context() -> None:
    records = validate_semantics(
        "Return states with the most customer records.",
        aggregate_plan("customer count"),
        "SELECT state, COUNT(DISTINCT customer_id) c FROM customers "
        "GROUP BY state ORDER BY c DESC LIMIT 1",
    )
    month = validate_semantics(
        "Tháng nào có nhiều đơn canceled nhất?",
        aggregate_plan("order count"),
        "SELECT STRFTIME('%m', purchased_at), COUNT(*) c FROM orders "
        "GROUP BY 1 ORDER BY c DESC LIMIT 1",
    )
    assert "RECORD_COUNT_MUST_NOT_BE_DISTINCT" in records.signals
    assert "YEAR_MONTH_CONTEXT_LOST" in month.signals


def test_olist_business_rules_do_not_leak_into_cross_domain_database() -> None:
    report = validate_semantics(
        "How many products have more than one photo?",
        aggregate_plan("product count"),
        "SELECT COUNT(*) FROM photos WHERE photo_count > 1",
        db_id="generic_photos",
    )
    assert report.accepted


def test_explicit_olist_status_and_customer_identity_are_proof_checked() -> None:
    wrong_status = validate_semantics(
        "Có bao nhiêu đơn hàng đã hủy?",
        aggregate_plan("order count"),
        "SELECT COUNT(*) FROM olist_order_reviews_dataset WHERE review_row_id IS NOT NULL",
        db_id="olist",
    )
    wrong_identity = validate_semantics(
        "Có bao nhiêu người mua duy nhất theo customer_unique_id?",
        aggregate_plan("customer count"),
        "SELECT COUNT(DISTINCT customer_id) FROM olist_orders_dataset",
        db_id="olist",
    )
    assert "EXPLICIT_ORDER_STATUS_MISMATCH" in wrong_status.signals
    assert "EXPLICIT_CUSTOMER_UNIQUE_ID_MISSING" in wrong_identity.signals


def test_returning_customer_scalar_rejects_top_level_grouping() -> None:
    report = validate_semantics(
        "Có bao nhiêu khách hàng quay lại với hơn một đơn hàng?",
        aggregate_plan("returning customer count"),
        "SELECT COUNT(DISTINCT customer_unique_id) FROM customers "
        "GROUP BY customer_unique_id HAVING COUNT(*) > 1",
        db_id="olist",
    )
    assert "RETURNING_CUSTOMER_REQUIRES_OUTER_COUNT" in report.signals


def test_ordered_distribution_forbids_unrequested_top_one() -> None:
    mistaken_plan = LogicalPlan(
        question_language="en",
        task_type="ranking",
        metrics=["order count"],
        dimensions=["status"],
        limit=1,
    )
    report = validate_semantics(
        "List order counts by status ordered from highest count, breaking ties by status.",
        mistaken_plan,
        "SELECT order_status, COUNT(*) c FROM orders GROUP BY order_status "
        "ORDER BY c DESC, order_status DESC LIMIT 1",
    )
    assert "DISTRIBUTION_LIMIT_UNREQUESTED" in report.signals
    assert "ALPHABETICAL_TIE_BREAK_MISSING" in report.signals
    assert "TOP_K_MISSING_LIMIT" not in report.signals

    corrected = validate_semantics(
        "List order counts by status ordered from highest count, breaking ties by status.",
        mistaken_plan,
        "SELECT order_status, COUNT(*) c FROM orders GROUP BY order_status "
        "ORDER BY c DESC, order_status ASC",
    )
    assert corrected.accepted


def test_safety_default_limit_is_not_mistaken_for_user_requested_limit(tmp_path) -> None:
    database = tmp_path / "distribution.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE orders(status TEXT)")
        connection.executemany("INSERT INTO orders VALUES (?)", [("done",), ("new",)])
    catalog = SQLiteIntrospector().inspect(database, "olist")
    plan = LogicalPlan(
        question_language="en",
        task_type="ranking",
        metrics=["order count"],
        dimensions=["status"],
        limit=1,
    )
    report, result = ValidationService().run(
        database,
        "SELECT status, COUNT(*) c FROM orders GROUP BY status ORDER BY c DESC, status ASC",
        catalog,
        question="List order counts by status ordered from highest count, breaking ties by status.",
        plan=plan,
    )
    assert report.accepted
    assert result is not None and len(result.rows) == 2


def test_olist_role_proof_rejects_payment_and_category_population_substitution() -> None:
    payment = validate_semantics(
        "Which payment type has the most payment records? Return type and count.",
        aggregate_plan("payment count"),
        "SELECT distinct_payment_type_count, COUNT(*) FROM order_payment_totals "
        "GROUP BY distinct_payment_type_count ORDER BY 2 DESC LIMIT 1",
        db_id="olist",
    )
    category = validate_semantics(
        "Có bao nhiêu sản phẩm thiếu danh mục?",
        aggregate_plan("product count"),
        "SELECT COUNT(*) FROM products_semantic WHERE product_category_name IS NULL "
        "OR product_category_name_english IS NULL",
        db_id="olist",
    )
    assert "PAYMENT_TYPE_RECORD_GRAIN_MISMATCH" in payment.signals
    assert "PRODUCT_CATEGORY_NULL_POPULATION_MISMATCH" in category.signals


def test_review_frequency_requires_raw_grain_and_deterministic_tie_break() -> None:
    question = "Điểm review nào xuất hiện nhiều nhất? Trả về điểm và số review."
    wrong = validate_semantics(
        question,
        aggregate_plan("review count"),
        "SELECT maximum_review_score, review_row_count FROM order_review_summary "
        "ORDER BY review_row_count DESC LIMIT 1",
        db_id="olist",
    )
    correct = validate_semantics(
        question,
        aggregate_plan("review count"),
        "SELECT review_score, COUNT(*) AS review_count "
        "FROM olist_order_reviews_dataset GROUP BY review_score "
        "ORDER BY review_count DESC, review_score ASC LIMIT 1",
        db_id="olist",
    )
    assert "REVIEW_FREQUENCY_GRAIN_MISMATCH" in wrong.signals
    assert "FREQUENCY_TIE_BREAK_MISSING" in wrong.signals
    assert correct.accepted


def test_olist_role_proof_accepts_exact_payment_and_category_populations() -> None:
    payment = validate_semantics(
        "Which payment type has the most payment records? Return type and count.",
        aggregate_plan("payment count"),
        "SELECT payment_type, COUNT(*) c FROM olist_order_payments_dataset "
        "GROUP BY payment_type ORDER BY c DESC LIMIT 1",
        db_id="olist",
    )
    category = validate_semantics(
        "Có bao nhiêu sản phẩm thiếu danh mục?",
        aggregate_plan("product count"),
        "SELECT COUNT(*) FROM olist_products_dataset WHERE product_category_name IS NULL",
        db_id="olist",
    )
    assert payment.accepted
    assert category.accepted
