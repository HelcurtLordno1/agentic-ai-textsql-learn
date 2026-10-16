"""Offline A1 diagnostics from saved traces and separately reviewed labels."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentic_text2sql.contracts.assessment import A1Trace, CheckOutcome
from agentic_text2sql_eval.inference_runner import SmokePrediction


class ReviewedA1Label(BaseModel):
    """Human review or a named offline evaluator; never an input to runtime."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    case_id: str
    review_status: Literal["REVIEWED"]
    reviewer: str = Field(min_length=1)
    semantic_error: bool
    # Labels must describe the initial draft, not the selected repair.
    contradictory_codes: tuple[str, ...] = ()
    candidate_correct: tuple[bool | None, ...] = ()
    final_correct: bool | None = None


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _metrics(tp: int, fp: int, fn: int, tn: int) -> dict[str, int | float | None]:
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": _ratio(tp, tp + fp),
        "recall": _ratio(tp, tp + fn),
        "false_positive_rate": _ratio(fp, fp + tn),
    }


def diagnose_a1(
    predictions: Sequence[SmokePrediction], labels: Sequence[ReviewedA1Label]
) -> dict[str, object]:
    prediction_ids = [p.case_id for p in predictions]
    label_ids = [label.case_id for label in labels]
    if len(set(prediction_ids)) != len(prediction_ids) or len(set(label_ids)) != len(label_ids):
        raise ValueError("Duplicate prediction or reviewed label IDs")
    if set(label_ids) - set(prediction_ids):
        raise ValueError("Reviewed labels contain cases absent from predictions")
    reviewed = {label.case_id: label for label in labels}
    detection = Counter[str]()
    clauses: dict[str, Counter[str]] = {}
    unknown = Counter[str]()
    routes = Counter[str]()
    costs = Counter[str]()
    execution = Counter[str]()
    quality = Counter[str]()
    latency_ms: list[float] = []
    for prediction in predictions:
        if prediction.result.assessment is None:
            raise ValueError("A1 diagnostics requires typed A1 traces for every prediction")
        trace = A1Trace.model_validate(prediction.result.assessment)
        costs["generation_requests"] += trace.actual_generation_requests
        costs["repair_attempted"] += int(trace.repair_attempted)
        costs["repair_admitted"] += int(trace.repair_admitted)
        costs["contract_eligible"] += int(
            bool(trace.repair_contract and trace.repair_contract.eligible)
        )
        costs["cpu_repairs"] += int(trace.repair_source == "deterministic")
        costs["llm_repairs"] += int(trace.repair_source == "model")
        costs["routed"] += int(trace.critic_routed)
        costs["critic_completed"] += int(
            "critic" in trace.prompts and "critic" not in trace.stage_errors
        )
        if trace.routing:
            routes.update(trace.routing.reasons)
        latency_ms.append(prediction.result.latency_ms.get("total", 0))
        if trace.draft_validation:
            execution["first_pass_executable"] += int(trace.draft_validation.accepted)
        execution["final_executable"] += int(prediction.result.status.value == "SUCCEEDED")
        checks = trace.draft_checks.findings if trace.draft_checks else ()
        findings = (*checks, *trace.model_findings)
        unknown.update(f.code for f in findings if f.outcome is CheckOutcome.UNKNOWN)
        detected = {f.code for f in findings if f.outcome is CheckOutcome.CONTRADICTION}
        label = reviewed.get(prediction.case_id)
        if label is None:
            continue
        key = (
            "tp"
            if detected and label.semantic_error
            else "fp"
            if detected
            else "fn"
            if label.semantic_error
            else "tn"
        )
        detection[key] += 1
        # Per-code recall is meaningful only with independently reviewed code labels.
        for code in detected | set(label.contradictory_codes):
            counts = clauses.setdefault(code, Counter())
            outcome = (
                "tp"
                if code in detected and code in label.contradictory_codes
                else "fp"
                if code in detected
                else "fn"
            )
            counts[outcome] += 1
        if label.candidate_correct:
            if len(label.candidate_correct) != len(trace.evaluations):
                raise ValueError("Candidate labels must align with every traced evaluation")
            first = label.candidate_correct[0]
            if first is not None:
                quality["first_pass_labeled"] += 1
                quality["first_pass_correct"] += int(first)
            if all(value is not None for value in label.candidate_correct):
                quality["pool_labeled"] += 1
                quality["pool_oracle_correct"] += int(any(label.candidate_correct))
        if label.final_correct is not None:
            quality["final_labeled"] += 1
            quality["final_correct"] += int(label.final_correct)
            if label.candidate_correct and label.candidate_correct[0] is not None:
                quality["repair_improvements"] += int(
                    not label.candidate_correct[0] and label.final_correct
                )
                quality["repair_regressions"] += int(
                    bool(label.candidate_correct[0]) and not label.final_correct
                )
    count = len(predictions)
    ordered_latency = sorted(latency_ms)
    return {
        "version": "a1-offline-diagnostics-v1",
        "cases": count,
        "reviewed": len(labels),
        "unreviewed": count - len(labels),
        "detector": _metrics(*(detection[key] for key in ("tp", "fp", "fn", "tn"))),
        "per_code": {
            code: {
                "tp": c["tp"],
                "fp": c["fp"],
                "fn": c["fn"],
                "precision": _ratio(c["tp"], c["tp"] + c["fp"]),
                "recall": _ratio(c["tp"], c["tp"] + c["fn"]),
            }
            for code, c in sorted(clauses.items())
        },
        "execution": dict(execution),
        "quality_counts": dict(quality),
        "first_pass_accuracy": _ratio(quality["first_pass_correct"], quality["first_pass_labeled"]),
        "final_accuracy": _ratio(quality["final_correct"], quality["final_labeled"]),
        "pool_oracle_accuracy": _ratio(quality["pool_oracle_correct"], quality["pool_labeled"]),
        "unknown_by_code": dict(sorted(unknown.items())),
        "routes": dict(sorted(routes.items())),
        "costs": dict(costs),
        "mean_generation_requests": _ratio(costs["generation_requests"], count),
        "latency_ms_mean": sum(latency_ms) / count if count else None,
        "latency_ms_p95": ordered_latency[max(0, (95 * count + 99) // 100 - 1)] if count else None,
        "interpretation": "Execution is not semantic accuracy; absent labels stay unknown.",
    }
