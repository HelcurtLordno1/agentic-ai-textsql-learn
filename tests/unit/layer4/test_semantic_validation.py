from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.validation import ErrorClass, ResultPreview
from agentic_text2sql.layer4_validation.result_validator import validate_result
from agentic_text2sql.layer4_validation.semantic_checks import validate_semantics


def aggregate_plan(metric: str = "customer count") -> LogicalPlan:
    return LogicalPlan(
        question_language="vi",
        task_type="aggregation",
        metrics=[metric],
        required_concepts=[],
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
