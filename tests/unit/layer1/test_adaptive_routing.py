from __future__ import annotations

import pytest

from agentic_text2sql.contracts.planning import AdaptiveRoute, LogicalPlan
from agentic_text2sql.layer1_reasoning.adaptive_routing import choose_adaptive_route
from agentic_text2sql.layer1_reasoning.decomposer import Decomposer


def _plan(
    *,
    task_type: str = "aggregation",
    metrics: list[str] | None = None,
    dimensions: list[str] | None = None,
    filters: list[str] | None = None,
    sort: list[str] | None = None,
    limit: int | None = None,
) -> LogicalPlan:
    return LogicalPlan.model_validate(
        {
            "question_language": "en",
            "task_type": task_type,
            "metrics": metrics or [],
            "dimensions": dimensions or [],
            "filters": filters or [],
            "sort": sort or [],
            "limit": limit,
        }
    )


@pytest.mark.parametrize(
    ("question", "plan"),
    [
        ("How many orders are there?", _plan(metrics=["order count"])),
        (
            "What is the average rating?",
            _plan(metrics=["average rating"]),
        ),
        (
            "How many orders arrived after the estimate?",
            _plan(metrics=["order count"], filters=["late arrival"]),
        ),
        (
            "Which state has the most sellers?",
            _plan(
                task_type="ranking",
                metrics=["seller count"],
                dimensions=["state"],
                sort=["seller count descending"],
                limit=1,
            ),
        ),
    ],
)
def test_scalar_and_single_role_queries_preserve_baseline(question: str, plan: LogicalPlan) -> None:
    decision = choose_adaptive_route(question, Decomposer().decompose(question), plan)
    assert decision.route is AdaptiveRoute.BASELINE_PRESERVE
    assert decision.signals == ("NO_EXPLICIT_COMPLEX_DEPENDENCY",)


@pytest.mark.parametrize(
    ("question", "plan", "signal"),
    [
        (
            "Find customers without any orders",
            _plan(task_type="set", dimensions=["customer"]),
            "EXPLICIT_SET_OR_COMPARISON",
        ),
        (
            "Show products whose revenue is above the average revenue",
            _plan(
                metrics=["revenue"],
                dimensions=["product"],
                filters=["above average"],
            ),
            "AGGREGATE_DEPENDENCY",
        ),
        (
            "Top 5 product categories by item revenue",
            _plan(
                task_type="ranking",
                metrics=["item revenue"],
                dimensions=["product category"],
                sort=["revenue descending"],
                limit=5,
            ),
            "MULTI_ROLE_GROUPED_RANKING",
        ),
        (
            "Tổng doanh thu trên mỗi danh mục sản phẩm",
            _plan(metrics=["revenue"], dimensions=["category"]),
            "MULTI_ROLE_GROUP_AGGREGATE",
        ),
        (
            "Count returning customers with more than one order",
            _plan(metrics=["customer count"], filters=["order count > 1"]),
            "GROUP_FILTER_AGGREGATE_DEPENDENCY",
        ),
        (
            "Có bao nhiêu khách hàng quay lại với hơn một đơn hàng?",
            _plan(metrics=["customer count"], filters=["order count > 1"]),
            "GROUP_FILTER_AGGREGATE_DEPENDENCY",
        ),
        (
            "Which review score appears most often?",
            _plan(task_type="ranking", metrics=["review count"], dimensions=["review score"]),
            "FREQUENCY_RANKING_DEPENDENCY",
        ),
        (
            "Which payment type has the most payment records? Return type and count.",
            _plan(task_type="ranking", metrics=["payment count"], dimensions=["payment type"]),
            "FREQUENCY_RANKING_DEPENDENCY",
        ),
        (
            "What is the average freight amount per order in cents rounded to 2 decimals?",
            _plan(metrics=["freight amount"]),
            "DERIVED_AVERAGE_DEPENDENCY",
        ),
        (
            "Trung bình mỗi đơn có bao nhiêu item?",
            _plan(metrics=["item count"]),
            "DERIVED_AVERAGE_DEPENDENCY",
        ),
        (
            "Số đơn hàng lớn nhất từng được ghi nhận cho một customer_unique_id là bao nhiêu?",
            _plan(metrics=["order count"]),
            "GROUPED_SCALAR_MAX_DEPENDENCY",
        ),
    ],
)
def test_explicit_complex_dependencies_activate_din(
    question: str, plan: LogicalPlan, signal: str
) -> None:
    decision = choose_adaptive_route(question, Decomposer().decompose(question), plan)
    assert decision.route is AdaptiveRoute.DIN_SQL_ENHANCE
    assert signal in decision.signals


def test_route_is_invariant_to_politeness_and_not_triggered_by_catalog_terms() -> None:
    plan = _plan(metrics=["order count"])
    variants = (
        "How many orders are there?",
        "Please tell me how many orders are there?",
        "Could you please count all orders in olist_orders_dataset?",
    )
    assert {
        choose_adaptive_route(question, Decomposer().decompose(question), plan).route
        for question in variants
    } == {AdaptiveRoute.BASELINE_PRESERVE}
