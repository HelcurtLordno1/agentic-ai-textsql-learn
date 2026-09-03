from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agentic_text2sql.contracts.planning import (
    ClarificationContext,
    ClarificationOption,
    Interpretation,
    LogicalPlan,
    QuestionAnalysisPrediction,
    QuestionCategory,
)
from agentic_text2sql.contracts.sql import DirectStatus, SqlCandidate
from agentic_text2sql.layer1_reasoning.decomposer import Decomposer
from agentic_text2sql.layer1_reasoning.planner import PlannerAgent
from agentic_text2sql.layer1_reasoning.question_analyst import QuestionAnalyst
from agentic_text2sql.layer1_reasoning.question_normalizer import QuestionNormalizer
from agentic_text2sql.layer1_reasoning.question_reliability import QuestionReliabilityService
from agentic_text2sql.layer1_reasoning.router import QueryRouter
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer3_generation.generator import GeneratorAgent
from agentic_text2sql.layer3_generation.normalizer import CandidateNormalizer
from agentic_text2sql.layer3_generation.prompt_builder import PromptBuilder
from agentic_text2sql.layer3_generation.service import GenerationService
from agentic_text2sql.layer4_validation.executor import ReadOnlySQLiteExecutor
from agentic_text2sql.layer4_validation.policy import SQLSafetyPolicy
from agentic_text2sql.layer6_application.query_service import DirectBaselineService

ROOT = Path(__file__).resolve().parents[2]
DATABASE = ROOT / "data/samples/synthetic_commerce_tiny.sqlite"


class QueueProvider:
    def __init__(self, responses: list[BaseModel]) -> None:
        self.responses = responses
        self.calls = 0
        self.prompts: list[str] = []

    def generate_structured(
        self, *, prompt: str, response_model: type[BaseModel], model: str | None = None
    ) -> Any:
        del response_model, model
        self.prompts.append(prompt)
        response = self.responses[self.calls]
        self.calls += 1
        return response


def interpretation(identifier: str = "i1", label: str = "Order count") -> Interpretation:
    return Interpretation(
        interpretation_id=identifier,
        metric="order count",
        grain="all orders",
        business_label=label,
    )


def build_service(provider: QueueProvider) -> DirectBaselineService:
    return DirectBaselineService(
        router=QueryRouter(),
        decomposer=Decomposer(),
        planner=PlannerAgent(provider, ROOT / "configs/prompts/planner_v2.j2"),
        generation=GenerationService(
            PromptBuilder(
                ROOT / "configs/prompts/generator_v4_cross_domain.j2",
                ROOT / "datasets/olist/business_glossary.yaml",
            ),
            GeneratorAgent(provider),
            CandidateNormalizer(),
            "fake-local",
        ),
        policy=SQLSafetyPolicy(),
        executor=ReadOnlySQLiteExecutor(),
        reliability=QuestionReliabilityService(
            QuestionNormalizer(),
            QueryRouter(),
            QuestionAnalyst(provider, ROOT / "configs/prompts/question_analyst_v1.j2"),
        ),
    )


def test_ambiguous_request_never_calls_planner_or_generator() -> None:
    prediction = QuestionAnalysisPrediction(
        category=QuestionCategory.AMBIGUOUS_FILTER_CRITERIA,
        interpretations=(
            interpretation("i1", "Revenue in 2017"),
            interpretation("i2", "Revenue in the last 12 months"),
        ),
        rationale="The requested recent period has two business meanings.",
        clarification_question="Which reporting period should be used?",
        clarification_options=(
            ClarificationOption(option_id="o1", label="Calendar year 2017"),
            ClarificationOption(option_id="o2", label="Last 12 months"),
        ),
    )
    provider = QueueProvider([prediction])
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")

    result = build_service(provider).run("Show recent revenue", DATABASE, catalog)

    assert result.status is DirectStatus.CLARIFY
    assert result.candidate is None and result.plan is None
    assert result.answerability is not None
    assert provider.calls == 1


def test_answerable_request_crosses_gate_and_executes() -> None:
    prediction = QuestionAnalysisPrediction(
        category=QuestionCategory.ANSWERABLE,
        interpretations=(interpretation(),),
        rationale="The order table supports this count.",
    )
    plan = LogicalPlan(
        question_language="en",
        task_type="aggregation",
        metrics=["order count"],
        required_concepts=["orders"],
    )
    provider = QueueProvider(
        [prediction, plan, SqlCandidate(sql="SELECT COUNT(*) FROM orders", confidence=1)]
    )
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")

    result = build_service(provider).run("How many orders?", DATABASE, catalog)

    assert result.status is DirectStatus.SUCCEEDED
    assert result.result_rows == [[4]]
    assert result.answerability is not None
    assert result.answerability.reason_code is QuestionCategory.ANSWERABLE
    assert result.prompt_versions["question_analyst"] == "question_analyst_v1"
    assert provider.calls == 3


def test_clarification_preserves_original_request_for_downstream_planning() -> None:
    prediction = QuestionAnalysisPrediction(
        category=QuestionCategory.ANSWERABLE,
        interpretations=(
            Interpretation(
                interpretation_id="i1",
                metric="order count",
                filters=("delivered orders",),
                grain="order",
                business_label="Top 5 months by delivered-order count",
            ),
        ),
        rationale="The user selected delivered orders.",
    )
    plan = LogicalPlan(
        question_language="en",
        task_type="ranking",
        metrics=["delivered order count"],
        dimensions=["month"],
        sort=["metric descending"],
        limit=5,
    )
    provider = QueueProvider(
        [prediction, plan, SqlCandidate(sql="SELECT COUNT(*) FROM orders", confidence=1)]
    )
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")
    context = ClarificationContext(
        parent_run_id="parent",
        original_question="Show the top 5 recent months by order count",
        assistant_question="Which order population?",
        options=(
            ClarificationOption(option_id="o1", label="Placed orders"),
            ClarificationOption(option_id="o2", label="Delivered orders"),
        ),
        user_response="Delivered orders",
    )

    result = build_service(provider).run(
        "Delivered orders", DATABASE, catalog, clarification_context=context
    )

    assert result.status is DirectStatus.SUCCEEDED
    assert result.clarification_context == context
    assert "Show the top 5 recent months" in provider.prompts[1]
    assert "User clarification: Delivered orders" in provider.prompts[1]


class RecordingGrounding:
    def __init__(self) -> None:
        self.question = ""

    def ground(self, question: str, plan: LogicalPlan) -> None:
        del plan
        self.question = question
        return None


def test_retrieval_keeps_original_vietnamese_and_appends_aliases() -> None:
    prediction = QuestionAnalysisPrediction(
        category=QuestionCategory.ANSWERABLE,
        interpretations=(interpretation(),),
        rationale="The order fact is available.",
    )
    plan = LogicalPlan(
        question_language="vi",
        task_type="aggregation",
        metrics=["order count"],
    )
    provider = QueueProvider(
        [prediction, plan, SqlCandidate(sql="SELECT COUNT(*) FROM orders", confidence=1)]
    )
    service = build_service(provider)
    grounding = RecordingGrounding()
    service.grounding = grounding  # type: ignore[assignment]
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")

    result = service.run("Có bao nhiêu đơn hàng đã được giao?", DATABASE, catalog)

    assert result.status is DirectStatus.SUCCEEDED
    assert grounding.question.startswith("Có bao nhiêu đơn hàng đã được giao?")
    assert "don hang->order" not in grounding.question
    assert "co bao nhieu order order status delivered" in grounding.question
