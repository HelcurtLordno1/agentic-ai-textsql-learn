from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.layer1_reasoning.decomposer import Decomposer
from agentic_text2sql.layer1_reasoning.planner import PLANNER_PROMPT_VERSION, PlannerAgent

ROOT = Path(__file__).resolve().parents[3]


class RecordingProvider:
    def __init__(self) -> None:
        self.prompt = ""

    def generate_structured(
        self, *, prompt: str, response_model: type[BaseModel], model: str | None = None
    ) -> Any:
        del response_model, model
        self.prompt = prompt
        return LogicalPlan(
            question_language="vi",
            task_type="ranking",
            metrics=["product revenue"],
            dimensions=["category"],
            filters=[],
            sort=["product revenue descending"],
            limit=5,
            required_concepts=["product revenue"],
            ambiguities=[],
            assumptions=["all statuses"],
        )


def test_decomposer_extracts_hints_without_sql() -> None:
    result = Decomposer().decompose("Top 5 danh mục theo doanh thu năm 2017")
    assert result.question_language == "vi"
    assert result.metric_hints == ["revenue"]
    assert result.dimension_hints == ["category", "time"]
    assert result.limit_hint == 5
    assert result.time_hints == ["2017"]
    assert "select" not in result.model_dump_json().lower()


def test_planner_uses_versioned_schema_agnostic_prompt() -> None:
    provider = RecordingProvider()
    planner = PlannerAgent(provider, ROOT / "configs/prompts/planner_v1.j2")
    plan = planner.plan(
        "Top 5 danh mục theo doanh thu", Decomposer().decompose("Top 5 danh mục theo doanh thu")
    )
    assert plan.limit == 5
    assert PLANNER_PROMPT_VERSION == "planner_v1"
    assert "Do not produce SQL" in provider.prompt
    assert "Required JSON Schema" in provider.prompt
    assert "olist_orders_dataset" not in provider.prompt
