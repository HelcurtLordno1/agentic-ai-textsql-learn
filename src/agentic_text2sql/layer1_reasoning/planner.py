"""One-shot schema-agnostic structured planner."""

from __future__ import annotations

import json
import re
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from agentic_text2sql.adapters.llm.base import StructuredLLM
from agentic_text2sql.contracts.planning import DecomposedQuestion, LogicalPlan

PLANNER_PROMPT_VERSION = "planner_v2"


class PlannerAgent:
    def __init__(self, provider: StructuredLLM, template_path: Path) -> None:
        self.provider = provider
        self.template_path = template_path

    def plan(self, question: str, decomposition: DecomposedQuestion) -> LogicalPlan:
        template = Environment(undefined=StrictUndefined, autoescape=False).from_string(
            self.template_path.read_text(encoding="utf-8")
        )
        prompt = template.render(
            question=question,
            decomposition=decomposition.model_dump_json(indent=2),
            output_schema=json.dumps(LogicalPlan.model_json_schema(), ensure_ascii=False),
        )
        generated = self.provider.generate_structured(prompt=prompt, response_model=LogicalPlan)
        return align_plan(question, decomposition, generated)


def align_plan(
    question: str, decomposition: DecomposedQuestion, generated: LogicalPlan
) -> LogicalPlan:
    """Apply deterministic question constraints that the model is not allowed to weaken."""
    lowered = question.casefold()
    updates: dict[str, object] = {}
    if decomposition.limit_hint is not None:
        updates["limit"] = decomposition.limit_hint
    if decomposition.sort_hints:
        updates["sort"] = decomposition.sort_hints
    asks_ranked_rows = (
        bool(re.search(r"\bnhiều\b.{0,40}\bnhất\b", lowered))
        or any(
            phrase in lowered
            for phrase in ("most ", "top ", "nhiều nhất", "cao nhất", "xuất hiện nhiều nhất")
        )
    ) and not any(phrase in lowered for phrase in ("what is the maximum", "lớn nhất từng"))
    if asks_ranked_rows:
        updates["task_type"] = "ranking"

    asks_scalar = any(
        phrase in lowered
        for phrase in ("how many", "có bao nhiêu", "là bao nhiêu", "what is the average")
    )
    explicitly_grouped = any(
        phrase in lowered for phrase in (" by ", " theo ", "per state", "mỗi ", "each ", "top ")
    )
    if asks_scalar and not explicitly_grouped and not asks_ranked_rows:
        updates["task_type"] = "aggregation"
        updates["dimensions"] = []
    asks_returning_customer = ("returning customer" in lowered or "quay lại" in lowered) and any(
        token in lowered for token in ("customer", "khách hàng")
    )
    if asks_returning_customer and asks_scalar:
        updates["task_type"] = "aggregation"
        updates["metrics"] = ["returning customer count"]
        updates["dimensions"] = []
    asks_scalar_maximum = any(
        phrase in lowered for phrase in ("what is the maximum", "lớn nhất từng")
    )
    if asks_scalar_maximum:
        updates["task_type"] = "aggregation"
        updates["dimensions"] = []
        updates["sort"] = []
        updates["limit"] = None
    return generated.model_copy(update=updates)
