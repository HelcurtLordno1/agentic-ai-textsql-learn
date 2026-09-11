"""Conservative, schema-agnostic activation policy for adaptive DIN-SQL.

The policy intentionally defaults to the frozen P6 path. DIN-SQL is an intervention for queries
whose requested shape explicitly needs decomposition; semantic catalog coverage alone is never a
reason to replace a baseline EASY query.
"""

from __future__ import annotations

import re

from agentic_text2sql.contracts.planning import (
    AdaptiveRoute,
    AdaptiveRouteDecision,
    DecomposedQuestion,
    LogicalPlan,
)

_NESTED_OR_SET_PATTERNS = (
    re.compile(r"\b(without|except|intersect|union|never|not\s+in)\b"),
    re.compile(r"\b(không có|chưa từng|ngoại trừ|giao của|hợp của)\b"),
)
_PER_GROUP_PATTERNS = (
    re.compile(r"\b(per|for each|within each|by each)\b"),
    re.compile(r"\b(mỗi|trên mỗi|theo từng)\b"),
)
_COMPARATIVE_AGGREGATE_PATTERNS = (
    re.compile(r"\b(above|below|greater than|less than)\s+(the\s+)?(average|total)\b"),
    re.compile(r"\b(cao hơn|thấp hơn|lớn hơn|nhỏ hơn)\s+(mức\s+)?(trung bình|tổng)\b"),
)


def choose_adaptive_route(
    question: str,
    decomposition: DecomposedQuestion,
    baseline_plan: LogicalPlan,
) -> AdaptiveRouteDecision:
    """Select DIN from explicit structure, never catalog coverage or case identity."""
    normalized = " ".join(question.casefold().split())
    signals: list[str] = []

    if baseline_plan.task_type == "set" or decomposition.set_operation_hint is not None:
        signals.append("EXPLICIT_SET_OR_COMPARISON")
    if any(pattern.search(normalized) for pattern in _NESTED_OR_SET_PATTERNS):
        signals.append("EXPLICIT_NESTED_OR_ANTI_JOIN")
    if any(pattern.search(normalized) for pattern in _COMPARATIVE_AGGREGATE_PATTERNS):
        signals.append("AGGREGATE_DEPENDENCY")

    grouped = bool(baseline_plan.dimensions or decomposition.dimension_hints)
    ranked = baseline_plan.task_type == "ranking" or bool(
        baseline_plan.sort or baseline_plan.limit or decomposition.sort_hints
    )
    per_group = any(pattern.search(normalized) for pattern in _PER_GROUP_PATTERNS)
    entity_roots = {value.removesuffix("s") for value in decomposition.entity_hints}
    independent_metrics = {
        value
        for value in decomposition.metric_hints
        if value.removesuffix(" count").removesuffix("s") not in entity_roots
    }
    multiple_business_roles = (
        len({*entity_roots, *independent_metrics, *decomposition.dimension_hints}) >= 3
    )
    if grouped and ranked and multiple_business_roles:
        signals.append("MULTI_ROLE_GROUPED_RANKING")
    if grouped and per_group and multiple_business_roles:
        signals.append("MULTI_ROLE_GROUP_AGGREGATE")

    if signals:
        return AdaptiveRouteDecision(
            route=AdaptiveRoute.DIN_SQL_ENHANCE,
            signals=tuple(dict.fromkeys(signals)),
        )
    return AdaptiveRouteDecision(
        route=AdaptiveRoute.BASELINE_PRESERVE,
        signals=("NO_EXPLICIT_COMPLEX_DEPENDENCY",),
    )
