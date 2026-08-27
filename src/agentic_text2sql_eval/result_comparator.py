"""Paired, case-preserving comparison of two frozen evaluation reports."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CaseTransition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    baseline_correct: bool
    challenger_correct: bool
    transition: str


class PairedComparison(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline_evaluation_id: str
    challenger_evaluation_id: str
    case_count: int = Field(ge=1)
    baseline_correct: int = Field(ge=0)
    challenger_correct: int = Field(ge=0)
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    unchanged_correct: int = Field(ge=0)
    unchanged_incorrect: int = Field(ge=0)
    net_change: int
    transitions: tuple[CaseTransition, ...]


def _case_correctness(report: dict[str, Any]) -> dict[str, bool]:
    if report.get("release_status") != "complete":
        raise ValueError("paired comparison requires complete reports")
    details = report.get("details")
    if not isinstance(details, list) or not details:
        raise ValueError("paired comparison requires non-empty case details")
    correctness: dict[str, bool] = {}
    for item in details:
        if not isinstance(item, dict) or "id" not in item or "result_correct" not in item:
            raise ValueError("report contains an invalid case detail")
        case_id = str(item["id"])
        if case_id in correctness:
            raise ValueError(f"report contains duplicate case ID: {case_id}")
        correctness[case_id] = bool(item["result_correct"])
    return correctness


def compare_reports(baseline: dict[str, Any], challenger: dict[str, Any]) -> PairedComparison:
    baseline_cases = _case_correctness(baseline)
    challenger_cases = _case_correctness(challenger)
    if set(baseline_cases) != set(challenger_cases):
        raise ValueError("paired reports must contain exactly the same case IDs")
    transitions: list[CaseTransition] = []
    counts = {"win": 0, "loss": 0, "unchanged_correct": 0, "unchanged_incorrect": 0}
    for case_id in sorted(baseline_cases):
        before = baseline_cases[case_id]
        after = challenger_cases[case_id]
        if not before and after:
            transition = "win"
        elif before and not after:
            transition = "loss"
        elif before:
            transition = "unchanged_correct"
        else:
            transition = "unchanged_incorrect"
        counts[transition] += 1
        transitions.append(
            CaseTransition(
                case_id=case_id,
                baseline_correct=before,
                challenger_correct=after,
                transition=transition,
            )
        )
    return PairedComparison(
        baseline_evaluation_id=str(baseline.get("evaluation_id", "unknown")),
        challenger_evaluation_id=str(challenger.get("evaluation_id", "unknown")),
        case_count=len(transitions),
        baseline_correct=sum(baseline_cases.values()),
        challenger_correct=sum(challenger_cases.values()),
        wins=counts["win"],
        losses=counts["loss"],
        unchanged_correct=counts["unchanged_correct"],
        unchanged_incorrect=counts["unchanged_incorrect"],
        net_change=counts["win"] - counts["loss"],
        transitions=tuple(transitions),
    )
