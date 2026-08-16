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


def validate_semantics(
    question: str, plan: LogicalPlan, sql: str, *, db_id: str | None = None
) -> ValidationReport:
    """Return only high-precision, gold-independent semantic suspicions."""
    statement = parse_one(sql)
    normalized_question = question.casefold()
    signals: list[str] = []
    select = statement if isinstance(statement, exp.Select) else statement.find(exp.Select)
    order = statement.args.get("order")
    ordered = list(order.expressions) if isinstance(order, exp.Order) else []
    sql_lower = sql.casefold()
    olist_rules = db_id in {None, "olist"}

    ranking_language = bool(re.search(r"\bnhiều\b.{0,40}\bnhất\b", normalized_question)) or any(
        phrase in normalized_question
        for phrase in (
            "most ",
            "top ",
            "nhiều nhất",
            "cao nhất",
            "lớn nhất",
            "xuất hiện nhiều nhất",
        )
    )
    requested_top = re.search(r"\btop\s+(\d+)\b", normalized_question)
    expects_ranked_rows = ranking_language and not any(
        phrase in normalized_question
        for phrase in ("là bao nhiêu", "what is the maximum", "maximum number")
    )
    if expects_ranked_rows:
        if not ordered:
            signals.append("RANKING_ORDER_MISSING")
        elif not bool(ordered[0].args.get("desc")):
            signals.append("RANKING_PRIMARY_NOT_DESC")
        expected_limit = plan.limit or (int(requested_top.group(1)) if requested_top else 1)
        limit = statement.args.get("limit")
        limit_value = limit.expression if isinstance(limit, exp.Limit) else None
        try:
            actual_limit = int(limit_value.this) if isinstance(limit_value, exp.Literal) else None
        except (TypeError, ValueError):
            actual_limit = None
        if actual_limit != expected_limit:
            signals.append("RANKING_LIMIT_MISMATCH")

    asks_alphabetical_tie_break = any(
        phrase in normalized_question
        for phrase in ("alphabetical tie-break", "hòa thì", "tie-break by")
    )
    if asks_alphabetical_tie_break and (len(ordered) < 2 or bool(ordered[1].args.get("desc"))):
        signals.append("ALPHABETICAL_TIE_BREAK_MISSING")

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
    ) and any(token in normalized_question for token in ("customer", "khách hàng"))
    uses_repeat_customer_view = "customer_order_facts" in set(
        re.findall(r"[a-z_][a-z0-9_]*", sql_lower)
    )
    if (
        olist_rules
        and asks_returning_customer
        and "customer_unique_id" not in sql_lower
        and not uses_repeat_customer_view
    ):
        signals.append("CUSTOMER_IDENTITY_NOT_UNIQUE")
    if (
        olist_rules
        and asks_returning_customer
        and uses_repeat_customer_view
        and not re.search(r"order_count\s*>\s*1\b", sql_lower)
    ):
        signals.append("RETURNING_CUSTOMER_REPEAT_FILTER_MISSING")
    if olist_rules and asks_returning_customer and select is not None and len(select.selects) != 1:
        signals.append("RETURNING_CUSTOMER_OUTPUT_SHAPE")

    asks_late_delivery = (
        "giao trễ" in normalized_question
        or "giao hàng trễ" in normalized_question
        or "late deliver" in normalized_question
        or "delivered late" in normalized_question
    )
    if (
        olist_rules
        and asks_late_delivery
        and re.search(r"order_status\s*=\s*['\"]delivered['\"]", sql_lower)
    ):
        signals.append("DELIVERY_POPULATION_NARROWED_BY_STATUS")

    asks_scalar_maximum = any(
        phrase in normalized_question
        for phrase in ("lớn nhất từng", "what is the maximum", "maximum number")
    ) and any(phrase in normalized_question for phrase in ("bao nhiêu", "what is", "number"))
    if asks_scalar_maximum and statement.find(exp.Max) is None:
        signals.append("SCALAR_MAXIMUM_AGGREGATE_MISSING")

    asks_record_count = " record" in f" {normalized_question}"
    if asks_record_count and statement.find(exp.Distinct) is not None:
        signals.append("RECORD_COUNT_MUST_NOT_BE_DISTINCT")

    asks_freight_per_order = (
        "freight" in normalized_question and "per order" in normalized_question and asks_average
    )
    if (
        olist_rules
        and asks_freight_per_order
        and not {
            "order_item_totals",
            "freight_cents",
        }.issubset(set(re.findall(r"[a-z_][a-z0-9_]*", sql_lower)))
    ):
        signals.append("FREIGHT_PER_ORDER_GRAIN_MISMATCH")

    asks_multiple_review_rows = "review row" in normalized_question and any(
        phrase in normalized_question for phrase in ("nhiều", "more than one", "> 1")
    )
    if (
        olist_rules
        and asks_multiple_review_rows
        and not {
            "order_review_summary",
            "review_row_count",
        }.issubset(set(re.findall(r"[a-z_][a-z0-9_]*", sql_lower)))
    ):
        signals.append("MULTIPLE_REVIEW_ROWS_RULE_MISSING")

    asks_multiple_photos = "photo" in normalized_question and any(
        phrase in normalized_question for phrase in ("more than one", "nhiều hơn một", "> 1")
    )
    if olist_rules and asks_multiple_photos and "product_photos_qty" not in sql_lower:
        signals.append("PRODUCT_PHOTO_QUANTITY_FILTER_MISSING")

    groups_month_only = bool(re.search(r"strftime\s*\(\s*['\"]%m['\"]", sql_lower))
    if "tháng nào" in normalized_question and groups_month_only:
        signals.append("YEAR_MONTH_CONTEXT_LOST")

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
