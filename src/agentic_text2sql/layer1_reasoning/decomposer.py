"""Clause-level hints without generating SQL or chain-of-thought."""

from __future__ import annotations

import re
from typing import Literal

from agentic_text2sql.contracts.planning import DecomposedQuestion

METRICS = {
    "revenue": ("revenue", "doanh thu"),
    "freight": ("freight", "shipping fee", "phí vận chuyển"),
    "paid value": ("paid value", "payment value", "thanh toán"),
    "order count": ("orders", "order count", "đơn hàng", "số đơn"),
    "customer count": ("customers", "customer count", "khách hàng"),
    "review score": ("review", "rating", "đánh giá", "điểm"),
    "delivery": ("delivery", "delivered", "giao hàng", "giao trễ"),
}
DIMENSIONS = {
    "category": ("category", "danh mục"),
    "state": ("state", "bang", "tiểu bang"),
    "seller": ("seller", "người bán"),
    "customer": ("customer", "khách hàng"),
    "time": ("year", "month", "năm", "tháng"),
    "payment type": ("payment type", "payment method", "phương thức thanh toán"),
}


def _language(question: str) -> Literal["vi", "en", "other"]:
    lowered = question.casefold()
    if any(
        token in lowered for token in ("đơn", "hàng", "doanh thu", "khách", "phí", "điểm", "nhiều")
    ):
        return "vi"
    if re.search(r"\b(the|how|what|which|orders?|customers?)\b", lowered):
        return "en"
    return "other"


class Decomposer:
    def decompose(self, question: str) -> DecomposedQuestion:
        lowered = question.casefold()
        metrics = [name for name, aliases in METRICS.items() if any(x in lowered for x in aliases)]
        dimensions = [
            name for name, aliases in DIMENSIONS.items() if any(x in lowered for x in aliases)
        ]
        limit_match = re.search(
            r"\b(?:top|limit|return|trả về)\s+(\d+)\b|"
            r"\b(\d+)\s+(?:\w+\s+){0,3}(?:cao nhất|hàng đầu|nhiều .+ nhất)\b",
            lowered,
        )
        limit = int(next(value for value in limit_match.groups() if value)) if limit_match else None
        asks_superlative = bool(re.search(r"\bnhiều\b.{0,40}\bnhất\b", lowered)) or any(
            value in lowered
            for value in ("most", "highest", "nhiều nhất", "cao nhất", "xuất hiện nhiều nhất")
        )
        asks_scalar_maximum = any(
            value in lowered for value in ("what is the maximum", "lớn nhất từng")
        )
        if asks_superlative and not asks_scalar_maximum and limit is None:
            limit = 1
        filters = []
        for value in ("delivered", "canceled", "unavailable", "giao thành công", "đã hủy"):
            if value in lowered:
                filters.append(value)
        if any(value in lowered for value in ("delivered late", "late delivery", "giao trễ")):
            filters = [value for value in filters if value != "delivered"]
        sort = ["metric descending"] if ("top" in lowered or asks_superlative) else []
        if any(value in lowered for value in ("tie-break", "hòa thì")):
            sort.append("dimension ascending tie-break")
        time_hints = re.findall(r"\b20\d{2}\b", lowered)
        return DecomposedQuestion(
            question_language=_language(question),
            metric_hints=metrics,
            dimension_hints=dimensions,
            filter_hints=filters,
            sort_hints=sort,
            limit_hint=limit,
            time_hints=time_hints,
            set_operation_hint="comparison"
            if any(x in lowered for x in ("compare", "so sánh"))
            else None,
            rationale="Deterministic lexical clause hints; semantic planning is delegated once.",
        )
