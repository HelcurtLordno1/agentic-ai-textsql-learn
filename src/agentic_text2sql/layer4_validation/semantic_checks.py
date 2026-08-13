"""Conservative semantic checks using intent, SQL shape, and declared business rules."""

from __future__ import annotations

import re

from sqlglot import exp

from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.validation import (
    ErrorClass,
    ValidationReport,
    ValidationStatus,
)
from agentic_text2sql.layer4_validation.parser import parse_one


def validate_semantics(question: str, plan: LogicalPlan, sql: str) -> ValidationReport:
    """Return only high-precision, gold-independent semantic suspicions."""
    statement = parse_one(sql)
    normalized_question = question.casefold()
    signals: list[str] = []

    if plan.task_type == "ranking" or plan.limit is not None:
        if statement.args.get("order") is None:
            signals.append("TOP_K_MISSING_ORDER")
        if plan.limit is not None:
            limit = statement.args.get("limit")
            if limit is None:
                signals.append("TOP_K_MISSING_LIMIT")

    asks_average = any(
        token in normalized_question for token in ("average", "trung bình", "mean")
    ) or any(
        "avg" in metric.casefold() or "average" in metric.casefold() for metric in plan.metrics
    )
    if asks_average and statement.find(exp.Avg) is None:
        signals.append("AVERAGE_AGGREGATE_MISSING")

    asks_returning_customer = (
        "quay lại" in normalized_question or "returning customer" in normalized_question
    ) and "customer" in normalized_question
    sql_lower = sql.casefold()
    if asks_returning_customer and "customer_unique_id" not in sql_lower:
        signals.append("CUSTOMER_IDENTITY_NOT_UNIQUE")
    select = statement if isinstance(statement, exp.Select) else statement.find(exp.Select)
    if asks_returning_customer and select is not None and len(select.selects) != 1:
        signals.append("RETURNING_CUSTOMER_OUTPUT_SHAPE")

    asks_late_delivery = (
        "giao trễ" in normalized_question
        or "giao hàng trễ" in normalized_question
        or "late deliver" in normalized_question
    )
    if asks_late_delivery and re.search(r"order_status\s*=\s*['\"]delivered['\"]", sql_lower):
        signals.append("DELIVERY_POPULATION_NARROWED_BY_STATUS")

    if signals:
        return ValidationReport(
            accepted=False,
            status=ValidationStatus.SUSPICIOUS,
            error_class=ErrorClass.SEMANTIC_MISMATCH,
            safe_message="Query structure conflicts with deterministic semantic rules",
            signals=signals,
            repair_eligible=True,
        )
    return ValidationReport(accepted=True)
