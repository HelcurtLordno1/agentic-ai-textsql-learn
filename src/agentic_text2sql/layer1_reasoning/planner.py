"""One-shot schema-agnostic structured planner."""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from agentic_text2sql.adapters.llm.base import StructuredLLM
from agentic_text2sql.contracts.planning import DecomposedQuestion, LogicalPlan

PLANNER_PROMPT_VERSION = "planner_v1"


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
        return self.provider.generate_structured(prompt=prompt, response_model=LogicalPlan)
