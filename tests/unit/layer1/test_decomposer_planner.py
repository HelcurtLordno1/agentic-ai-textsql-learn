from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.layer1_reasoning.decomposer import Decomposer
from agentic_text2sql.layer1_reasoning.planner import (
    PLANNER_PROMPT_VERSION,
    PlannerAgent,
    align_plan,
)

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
    planner = PlannerAgent(provider, ROOT / "configs/prompts/planner_v2.j2")
    plan = planner.plan(
        "Top 5 danh mục theo doanh thu", Decomposer().decompose("Top 5 danh mục theo doanh thu")
    )
    assert plan.limit == 5
    assert PLANNER_PROMPT_VERSION == "planner_v2"
    assert "Do not produce SQL" in provider.prompt
    assert "Required JSON Schema" in provider.prompt
    assert "olist_orders_dataset" not in provider.prompt


def test_superlative_and_late_delivery_hints_are_deterministic() -> None:
    ranking = Decomposer().decompose(
        "Which seller state has the most records with alphabetical tie-break?"
    )
    late = Decomposer().decompose(
        "How many orders were delivered late based on actual versus estimated timestamp?"
    )
    assert ranking.limit_hint == 1
    assert ranking.sort_hints == ["metric descending", "dimension ascending tie-break"]
    assert "delivered" not in late.filter_hints


def test_plan_alignment_preserves_scalar_and_ranking_constraints() -> None:
    generated = LogicalPlan(
        question_language="vi",
        task_type="aggregation",
        metrics=["customer count", "order count"],
        dimensions=["customer"],
    )
    scalar_question = "Có bao nhiêu khách hàng quay lại với hơn một đơn hàng?"
    scalar = align_plan(scalar_question, Decomposer().decompose(scalar_question), generated)
    ranking_question = "Bang nào có nhiều khách hàng nhất, hòa thì bang tăng dần?"
    ranking = align_plan(ranking_question, Decomposer().decompose(ranking_question), generated)
    assert scalar.task_type == "aggregation"
    assert scalar.dimensions == []
    assert scalar.metrics == ["returning customer count"]
    assert ranking.task_type == "ranking"
    assert ranking.limit == 1
    assert ranking.sort == ["metric descending", "dimension ascending tie-break"]


def test_vietnamese_return_count_overrides_superlative_default() -> None:
    question = "Trả về 3 bang có nhiều khách hàng record nhất, hòa thì bang tăng dần."
    decomposition = Decomposer().decompose(question)
    assert decomposition.limit_hint == 3


def test_scalar_maximum_clears_model_ranking_shape() -> None:
    question = "Số đơn hàng lớn nhất từng được ghi nhận là bao nhiêu?"
    generated = LogicalPlan(
        question_language="vi",
        task_type="ranking",
        metrics=["order count"],
        dimensions=["customer"],
        sort=["metric descending"],
        limit=1,
    )
    aligned = align_plan(question, Decomposer().decompose(question), generated)
    assert aligned.task_type == "aggregation"
    assert aligned.dimensions == []
    assert aligned.sort == []
    assert aligned.limit is None
