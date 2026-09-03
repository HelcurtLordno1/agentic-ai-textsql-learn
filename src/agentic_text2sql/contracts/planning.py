"""Layer 1 planning and question-reliability contracts."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RouteIntent(StrEnum):
    QUERY = "QUERY"
    CLARIFY = "CLARIFY"
    UNSUPPORTED = "UNSUPPORTED"
    WRITE_REQUEST = "WRITE_REQUEST"


class RouteDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    intent: RouteIntent
    reason: str


class AnswerabilityOutcome(StrEnum):
    """Product decision made before any SQL planning or generation."""

    ANSWER = "ANSWER"
    CLARIFY = "CLARIFY"
    CANNOT_ANSWER = "CANNOT_ANSWER"
    SAFE_REJECT = "SAFE_REJECT"


class QuestionCategory(StrEnum):
    """PRACTIQ's nine-way taxonomy plus bounded product failure categories."""

    ANSWERABLE = "ANSWERABLE"
    AMBIGUOUS_SELECT_COLUMN = "AMBIGUOUS_SELECT_COLUMN"
    AMBIGUOUS_WHERE_COLUMN = "AMBIGUOUS_WHERE_COLUMN"
    AMBIGUOUS_VALUE = "AMBIGUOUS_VALUE"
    AMBIGUOUS_FILTER_CRITERIA = "AMBIGUOUS_FILTER_CRITERIA"
    NONEXISTENT_SELECT_COLUMN = "NONEXISTENT_SELECT_COLUMN"
    NONEXISTENT_WHERE_COLUMN = "NONEXISTENT_WHERE_COLUMN"
    NONEXISTENT_FILTER_VALUE = "NONEXISTENT_FILTER_VALUE"
    UNSUPPORTED_JOIN = "UNSUPPORTED_JOIN"
    MISSING_INTENT = "MISSING_INTENT"
    UNSUPPORTED_REQUEST = "UNSUPPORTED_REQUEST"
    WRITE_REQUEST = "WRITE_REQUEST"
    ANALYSIS_UNCERTAIN = "ANALYSIS_UNCERTAIN"


AMBIGUOUS_CATEGORIES = frozenset(
    {
        QuestionCategory.AMBIGUOUS_SELECT_COLUMN,
        QuestionCategory.AMBIGUOUS_WHERE_COLUMN,
        QuestionCategory.AMBIGUOUS_VALUE,
        QuestionCategory.AMBIGUOUS_FILTER_CRITERIA,
    }
)
UNANSWERABLE_CATEGORIES = frozenset(
    {
        QuestionCategory.NONEXISTENT_SELECT_COLUMN,
        QuestionCategory.NONEXISTENT_WHERE_COLUMN,
        QuestionCategory.NONEXISTENT_FILTER_VALUE,
        QuestionCategory.UNSUPPORTED_JOIN,
    }
)


class NormalizedQuestion(BaseModel):
    """Lossless question normalization with separate retrieval-friendly text."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    raw_text: str = Field(min_length=1, max_length=2000)
    normalized_text: str = Field(min_length=1, max_length=2000)
    search_text: str = Field(min_length=1, max_length=2400)
    question_language: Literal["vi", "en", "other"]
    aliases_applied: tuple[str, ...] = Field(default=(), max_length=20)


class Interpretation(BaseModel):
    """One business interpretation; deliberately contains no SQL."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    interpretation_id: str = Field(pattern=r"^i[1-3]$")
    metric: str | None = Field(default=None, max_length=160)
    dimensions: tuple[str, ...] = Field(default=(), max_length=6)
    filters: tuple[str, ...] = Field(default=(), max_length=8)
    grain: str | None = Field(default=None, max_length=160)
    assumptions: tuple[str, ...] = Field(default=(), max_length=6)
    business_label: str = Field(min_length=1, max_length=160)


class ClarificationOption(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    option_id: str = Field(pattern=r"^o[1-3]$")
    label: str = Field(min_length=1, max_length=160)


class QuestionAnalysisPrediction(BaseModel):
    """Schema-constrained response produced by the local question analyst."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    category: QuestionCategory
    interpretations: tuple[Interpretation, ...] = Field(min_length=1, max_length=3)
    rationale: str = Field(min_length=1, max_length=500)
    clarification_question: str | None = Field(default=None, max_length=300)
    clarification_options: tuple[ClarificationOption, ...] = Field(default=(), max_length=3)
    missing_evidence: tuple[str, ...] = Field(default=(), max_length=6)

    @model_validator(mode="after")
    def validate_category_payload(self) -> Self:
        if self.category in AMBIGUOUS_CATEGORIES:
            if not self.clarification_question or len(self.clarification_options) < 2:
                raise ValueError("ambiguous predictions require a question and 2-3 options")
        elif self.clarification_question is not None or self.clarification_options:
            raise ValueError("only ambiguous predictions may include clarification fields")
        return self


class AnswerabilityDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: AnswerabilityOutcome
    reason_code: QuestionCategory
    rationale: str = Field(min_length=1, max_length=500)
    interpretations: tuple[Interpretation, ...] = Field(default=(), max_length=3)
    clarification_question: str | None = Field(default=None, max_length=300)
    clarification_options: tuple[ClarificationOption, ...] = Field(default=(), max_length=3)
    missing_evidence: tuple[str, ...] = Field(default=(), max_length=6)
    source: Literal["rule", "local_llm", "fail_closed"]

    @model_validator(mode="after")
    def validate_outcome_payload(self) -> Self:
        if self.outcome is AnswerabilityOutcome.ANSWER and len(self.interpretations) != 1:
            raise ValueError("ANSWER requires exactly one accepted interpretation")
        if self.outcome is AnswerabilityOutcome.CLARIFY:
            if not self.clarification_question or len(self.clarification_options) < 2:
                raise ValueError("CLARIFY requires a question and 2-3 business options")
        elif self.clarification_question is not None or self.clarification_options:
            raise ValueError("only CLARIFY may include clarification fields")
        return self


class ClarificationContext(BaseModel):
    """Bounded four-turn context used to resolve a prior CLARIFY decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    parent_run_id: str = Field(min_length=1, max_length=100)
    original_question: str = Field(min_length=1, max_length=2000)
    assistant_question: str = Field(min_length=1, max_length=300)
    options: tuple[ClarificationOption, ...] = Field(min_length=2, max_length=3)
    user_response: str = Field(min_length=1, max_length=1000)


class DecomposedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_language: Literal["vi", "en", "other"]
    metric_hints: list[str] = Field(default_factory=list)
    dimension_hints: list[str] = Field(default_factory=list)
    filter_hints: list[str] = Field(default_factory=list)
    sort_hints: list[str] = Field(default_factory=list)
    limit_hint: int | None = Field(default=None, ge=1)
    time_hints: list[str] = Field(default_factory=list)
    set_operation_hint: str | None = None
    rationale: str = Field(max_length=500)


class LogicalPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_language: Literal["vi", "en", "other"]
    task_type: Literal["lookup", "aggregation", "ranking", "comparison", "set"]
    metrics: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    sort: list[str] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1)
    required_concepts: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
