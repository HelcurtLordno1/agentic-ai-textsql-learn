from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from agentic_text2sql.contracts.catalog import CatalogSnapshot, ColumnInfo, TableInfo
from agentic_text2sql.contracts.planning import (
    AnswerabilityDecision,
    AnswerabilityOutcome,
    ClarificationOption,
    Interpretation,
    QuestionAnalysisPrediction,
    QuestionCategory,
)
from agentic_text2sql.exceptions import StructuredOutputError
from agentic_text2sql.layer1_reasoning.question_analyst import QuestionAnalyst
from agentic_text2sql.layer1_reasoning.question_normalizer import QuestionNormalizer
from agentic_text2sql.layer1_reasoning.question_reliability import QuestionReliabilityService
from agentic_text2sql.layer1_reasoning.router import QueryRouter

ROOT = Path(__file__).resolve().parents[3]


class StubProvider:
    def __init__(self, response: BaseModel | Exception) -> None:
        self.response = response
        self.calls = 0
        self.prompt = ""

    def generate_structured(
        self, *, prompt: str, response_model: type[BaseModel], model: str | None = None
    ) -> Any:
        del response_model, model
        self.calls += 1
        self.prompt = prompt
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def catalog(db_id: str = "tiny") -> CatalogSnapshot:
    return CatalogSnapshot(
        db_id=db_id,
        tables=(
            TableInfo(
                name="orders",
                columns=(
                    ColumnInfo(name="order_id", data_type="TEXT"),
                    ColumnInfo(name="status", data_type="TEXT"),
                    ColumnInfo(name="revenue", data_type="REAL"),
                ),
            ),
        ),
        catalog_hash="12345678",
    )


def interpretation(identifier: str = "i1", label: str = "Order count") -> Interpretation:
    return Interpretation(
        interpretation_id=identifier,
        metric="order count",
        grain="all orders",
        business_label=label,
    )


def answerable_prediction() -> QuestionAnalysisPrediction:
    return QuestionAnalysisPrediction(
        category=QuestionCategory.ANSWERABLE,
        interpretations=(interpretation(),),
        rationale="The order fact and requested aggregate are available.",
    )


def test_normalizer_preserves_raw_and_adds_bilingual_typo_aliases() -> None:
    result = QuestionNormalizer().normalize("  Top catagory theo doanh thu sản phẩm  ")

    assert result.raw_text == "  Top catagory theo doanh thu sản phẩm  "
    assert result.normalized_text == "Top catagory theo doanh thu sản phẩm"
    assert result.search_text == "top category theo product revenue"
    assert result.question_language == "vi"
    assert "catagory->category" in result.aliases_applied
    assert "doanh thu san pham->product revenue" in result.aliases_applied


def test_normalizer_adds_status_alias_without_replacing_original_question() -> None:
    result = QuestionNormalizer().normalize("Có bao nhiêu đơn hàng đã được giao?")

    assert result.normalized_text == "Có bao nhiêu đơn hàng đã được giao?"
    assert "order status delivered" in result.search_text
    assert "da duoc giao->order status delivered" in result.aliases_applied


@pytest.mark.parametrize(
    ("question", "expected_alias"),
    [
        ("Tong phi van chuyen theo bang nguoi ban.", "seller"),
        ("So don tung thang trong nam 2017.", "monthly"),
        ("Nguoi ban nao co nhieu san pham ban nhat?", "sold item"),
        ("Co bao nhieu bang khach hang khac nhau?", "customer state"),
    ],
)
def test_normalizer_handles_diacriticless_business_phrases(
    question: str, expected_alias: str
) -> None:
    result = QuestionNormalizer().normalize(question)

    assert result.question_language == "vi"
    assert expected_alias in result.search_text


def test_ambiguous_contract_requires_business_question_and_choices() -> None:
    with pytest.raises(ValidationError):
        QuestionAnalysisPrediction(
            category=QuestionCategory.AMBIGUOUS_FILTER_CRITERIA,
            interpretations=(interpretation(),),
            rationale="Underage needs a threshold.",
        )


def test_schema_aware_analyst_maps_prediction_without_sql_or_rows() -> None:
    provider = StubProvider(answerable_prediction())
    analyst = QuestionAnalyst(provider, ROOT / "configs/prompts/question_analyst_v1.j2")

    decision = analyst.analyze(QuestionNormalizer().normalize("How many orders?"), catalog())

    assert decision.outcome is AnswerabilityOutcome.ANSWER
    assert decision.source == "local_llm"
    assert "orders" in provider.prompt
    assert '"rows":' not in provider.prompt
    assert "SELECT COUNT" not in provider.prompt


def test_rule_first_rejects_write_and_cannot_answer_olist_returns_without_llm() -> None:
    provider = StubProvider(answerable_prediction())
    service = QuestionReliabilityService(
        QuestionNormalizer(),
        QueryRouter(),
        QuestionAnalyst(provider, ROOT / "configs/prompts/question_analyst_v1.j2"),
    )

    _, write = service.evaluate("Delete every order", catalog("olist"))
    _, returns = service.evaluate("Tỷ lệ trả hàng là bao nhiêu?", catalog("olist"))

    assert write.outcome is AnswerabilityOutcome.SAFE_REJECT
    assert returns.outcome is AnswerabilityOutcome.CANNOT_ANSWER
    assert returns.reason_code is QuestionCategory.NONEXISTENT_SELECT_COLUMN
    assert provider.calls == 0


@pytest.mark.parametrize(
    "question",
    [
        "How many orders have delivered status?",
        "Count delivered oder records.",
        "Có bao nhiêu đơn hàng đã được giao?",
        "Count canceled oder records.",
        "How many orders have unavailable status?",
    ],
)
def test_explicit_olist_status_is_answerable_without_llm(question: str) -> None:
    provider = StubProvider(answerable_prediction())
    service = QuestionReliabilityService(
        QuestionNormalizer(),
        QueryRouter(),
        QuestionAnalyst(provider, ROOT / "configs/prompts/question_analyst_v1.j2"),
    )

    _, decision = service.evaluate(question, catalog("olist"))

    assert decision.outcome is AnswerabilityOutcome.ANSWER
    assert decision.source == "rule"
    assert decision.interpretations[0].filters[0].startswith("order status ")
    assert provider.calls == 0


def test_late_delivered_request_is_not_reduced_to_status_rule() -> None:
    provider = StubProvider(answerable_prediction())
    service = QuestionReliabilityService(
        QuestionNormalizer(),
        QueryRouter(),
        QuestionAnalyst(provider, ROOT / "configs/prompts/question_analyst_v1.j2"),
    )

    _, decision = service.evaluate("How many orders were delivered late?", catalog("olist"))

    assert decision.source == "local_llm"
    assert provider.calls == 1


def test_delivered_timestamp_request_preserves_full_analysis() -> None:
    provider = StubProvider(answerable_prediction())
    service = QuestionReliabilityService(
        QuestionNormalizer(),
        QueryRouter(),
        QuestionAnalyst(provider, ROOT / "configs/prompts/question_analyst_v1.j2"),
    )

    _, decision = service.evaluate(
        "How many delivered orders have a non-null delivery timestamp?", catalog("olist")
    )

    assert decision.source == "local_llm"
    assert provider.calls == 1


def test_malformed_local_analysis_fails_closed_before_sql() -> None:
    provider = StubProvider(StructuredOutputError("bad json"))
    service = QuestionReliabilityService(
        QuestionNormalizer(),
        QueryRouter(),
        QuestionAnalyst(provider, ROOT / "configs/prompts/question_analyst_v1.j2"),
    )

    _, decision = service.evaluate("Compare orders by status", catalog())

    assert decision.outcome is AnswerabilityOutcome.CLARIFY
    assert decision.reason_code is QuestionCategory.ANALYSIS_UNCERTAIN
    assert decision.source == "fail_closed"


def test_answerability_decision_rejects_clarification_payload_on_answer() -> None:
    with pytest.raises(ValidationError):
        AnswerabilityDecision(
            outcome=AnswerabilityOutcome.ANSWER,
            reason_code=QuestionCategory.ANSWERABLE,
            rationale="answerable",
            interpretations=(interpretation(),),
            clarification_question="Which one?",
            clarification_options=(
                ClarificationOption(option_id="o1", label="First"),
                ClarificationOption(option_id="o2", label="Second"),
            ),
            source="rule",
        )
