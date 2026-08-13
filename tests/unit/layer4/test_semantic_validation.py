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
