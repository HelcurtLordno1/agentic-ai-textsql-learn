from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.sql import DirectRunResult, DirectStatus, SqlCandidate
from agentic_text2sql.exceptions import StructuredOutputError
from agentic_text2sql.layer1_reasoning.decomposer import Decomposer
from agentic_text2sql.layer1_reasoning.planner import PlannerAgent
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
    def __init__(self, responses: list[BaseModel | Exception]) -> None:
        self.responses = responses
        self.calls = 0

    def generate_structured(
        self, *, prompt: str, response_model: type[BaseModel], model: str | None = None
    ) -> Any:
        del prompt, response_model, model
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


def plan() -> LogicalPlan:
    return LogicalPlan(
        question_language="en",
        task_type="aggregation",
        metrics=["order count"],
        required_concepts=["orders"],
    )


def service(provider: QueueProvider) -> DirectBaselineService:
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
    )


def run(provider: QueueProvider, question: str = "How many orders?") -> DirectRunResult:
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")
    return service(provider).run(question, DATABASE, catalog)


def test_direct_vertical_slice_succeeds_with_two_model_calls() -> None:
    provider = QueueProvider(
        [plan(), SqlCandidate(sql="SELECT COUNT(*) FROM orders", confidence=1)]
    )
    result = run(provider)
    assert result.status is DirectStatus.SUCCEEDED
    assert result.result_rows == [[4]]
    assert result.candidate is not None
    assert result.candidate.model_name == "fake-local"
    assert provider.calls == 2
    assert result.latency_ms["total"] >= 0


def test_malformed_planner_is_typed_model_error_not_crash() -> None:
    provider = QueueProvider([StructuredOutputError("malformed structured output")])
    result = run(provider)
    assert result.status is DirectStatus.MODEL_ERROR
    assert result.safe_message == "malformed structured output"
    assert "total" in result.latency_ms


def test_invalid_sql_is_typed_and_never_executes() -> None:
    provider = QueueProvider([plan(), SqlCandidate(sql="not sql", confidence=0.1)])
    result = run(provider)
    assert result.status is DirectStatus.INVALID_SQL
    assert "total" in result.latency_ms


def test_write_and_returns_stop_before_model() -> None:
    provider = QueueProvider([])
    write = run(provider, "Delete every order")
    returns = run(provider, "What is the return rate?")
    assert write.status is DirectStatus.WRITE_BLOCKED
    assert returns.status is DirectStatus.CLARIFY
    assert provider.calls == 0
    assert "total" in write.latency_ms and "total" in returns.latency_ms
