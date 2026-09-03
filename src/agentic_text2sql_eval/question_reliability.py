"""Gold-isolated metrics for the PRACTIQ-inspired question reliability gate."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ReliabilityLabel(StrEnum):
    ANSWER = "ANSWER"
    CLARIFY = "CLARIFY"
    CANNOT_ANSWER = "CANNOT_ANSWER"


class ReliabilityJudgment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    case_id: str = Field(min_length=1)
    expected: ReliabilityLabel
    predicted: ReliabilityLabel
    clarification_resolved: bool | None = None


class ReliabilityReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    case_count: int = Field(ge=1)
    macro_f1: float = Field(ge=0, le=1)
    ambiguity_recall: float = Field(ge=0, le=1)
    answerable_false_refusal: float = Field(ge=0, le=1)
    clarification_success: float | None = Field(default=None, ge=0, le=1)
    confusion: dict[str, dict[str, int]]


def evaluate_reliability(judgments: list[ReliabilityJudgment]) -> ReliabilityReport:
    if not judgments:
        raise ValueError("at least one reliability judgment is required")
    identifiers = [item.case_id for item in judgments]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("case_id values must be unique")
    labels = tuple(ReliabilityLabel)
    confusion = {
        expected.value: {predicted.value: 0 for predicted in labels} for expected in labels
    }
    for item in judgments:
        confusion[item.expected.value][item.predicted.value] += 1
    f1_values = []
    for label in labels:
        true_positive = confusion[label.value][label.value]
        false_positive = sum(
            confusion[other.value][label.value] for other in labels if other is not label
        )
        false_negative = sum(
            confusion[label.value][other.value] for other in labels if other is not label
        )
        denominator = 2 * true_positive + false_positive + false_negative
        f1_values.append(0.0 if denominator == 0 else (2 * true_positive) / denominator)
    ambiguous = [item for item in judgments if item.expected is ReliabilityLabel.CLARIFY]
    answerable = [item for item in judgments if item.expected is ReliabilityLabel.ANSWER]
    if not ambiguous or not answerable:
        raise ValueError("report requires both CLARIFY and ANSWER reference cases")
    resolved = [
        item.clarification_resolved for item in ambiguous if item.clarification_resolved is not None
    ]
    return ReliabilityReport(
        case_count=len(judgments),
        macro_f1=sum(f1_values) / len(f1_values),
        ambiguity_recall=sum(item.predicted is ReliabilityLabel.CLARIFY for item in ambiguous)
        / len(ambiguous),
        answerable_false_refusal=sum(
            item.predicted is not ReliabilityLabel.ANSWER for item in answerable
        )
        / len(answerable),
        clarification_success=(sum(resolved) / len(resolved) if resolved else None),
        confusion=confusion,
    )
