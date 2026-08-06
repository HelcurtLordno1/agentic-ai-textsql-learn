"""Deterministic intent routing before any model call."""

from __future__ import annotations

import re

from agentic_text2sql.contracts.planning import RouteDecision, RouteIntent

WRITE_PATTERNS = (
    r"\b(insert|update|delete|drop|alter|create|truncate|merge|attach|detach)\b",
    r"\b(xóa|xoá|thêm|chèn|cập nhật|sửa)\b.{0,30}\b(dữ liệu|bản ghi|bảng|database)\b",
)
UNSUPPORTED_DATA_PATTERNS = (
    r"\b(return rate|returns|returned|refund|refunds|refunded)\b",
    r"\b(trả hàng|hoàn hàng|hoàn tiền|tỷ lệ trả)\b",
)
GREETINGS = {
    "hi",
    "hello",
    "hey",
    "xin chào",
    "chào bạn",
    "cảm ơn",
    "thank you",
    "thanks",
}


class QueryRouter:
    def route(self, question: str) -> RouteDecision:
        normalized = " ".join(question.casefold().split())
        if not normalized or len(normalized) < 4:
            return RouteDecision(
                intent=RouteIntent.CLARIFY,
                reason="Question is empty or too short to identify a metric or entity",
            )
        if any(re.search(pattern, normalized) for pattern in WRITE_PATTERNS):
            return RouteDecision(
                intent=RouteIntent.WRITE_REQUEST,
                reason="Explicit database write or schema-change request",
            )
        if any(re.search(pattern, normalized) for pattern in UNSUPPORTED_DATA_PATTERNS):
            return RouteDecision(
                intent=RouteIntent.CLARIFY,
                reason="Olist has no returns or refunds facts; canceled orders are not returns",
            )
        if normalized.strip("!?. ") in GREETINGS:
            return RouteDecision(
                intent=RouteIntent.UNSUPPORTED,
                reason="Greeting or non-data request",
            )
        return RouteDecision(intent=RouteIntent.QUERY, reason="Read-oriented analytical question")
