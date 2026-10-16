"""Gold-separated draft/pool diagnostics; no labels flow back into runtime."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from agentic_text2sql.contracts.assessment import A1Trace, CandidateEvaluation
from agentic_text2sql.contracts.sql import DirectRunResult, DirectStatus


def score_saved_candidates(
    result: DirectRunResult,
    scorer: Callable[[CandidateEvaluation], bool | None],
) -> dict[str, Any] | None:
    if result.assessment is None:
        return None
    trace = A1Trace.model_validate(result.assessment)
    labels = [scorer(evaluation) for evaluation in trace.evaluations]
    missing_successful_snapshots = not labels and result.status is DirectStatus.SUCCEEDED
    return {
        "candidate_correct": labels,
        "candidate_origins": [evaluation.origin for evaluation in trace.evaluations],
        "first_pass_correct": labels[0]
        if labels
        else (None if missing_successful_snapshots else False),
        "pool_oracle_correct": (
            any(labels) if None not in labels and not missing_successful_snapshots else None
        ),
        "contract_eligible": bool(trace.repair_contract and trace.repair_contract.eligible),
        "repair_attempted": trace.repair_attempted,
        "repair_admitted": trace.repair_admitted,
        "repair_source": trace.repair_source,
        "generation_requests": trace.actual_generation_requests,
    }


def summarize_candidates(details: Sequence[dict[str, Any]]) -> dict[str, Any]:
    selected = [item for item in details if item.get("a1_candidates") is not None]
    first = [item for item in selected if item["a1_candidates"]["first_pass_correct"] is not None]
    pool = [item for item in selected if item["a1_candidates"]["pool_oracle_correct"] is not None]
    gains = sum(
        not item["a1_candidates"]["first_pass_correct"] and item["result_correct"] for item in first
    )
    losses = sum(
        item["a1_candidates"]["first_pass_correct"] and not item["result_correct"] for item in first
    )
    return {
        "traced_cases": len(selected),
        "first_pass_scored": len(first),
        "first_pass_accuracy": (
            sum(bool(item["a1_candidates"]["first_pass_correct"]) for item in first) / len(first)
            if first
            else None
        ),
        "pool_scored": len(pool),
        "pool_oracle_accuracy": (
            sum(bool(item["a1_candidates"]["pool_oracle_correct"]) for item in pool) / len(pool)
            if pool
            else None
        ),
        "gain": gains,
        "loss": losses,
        "net_gain": gains - losses,
        "generation_requests": sum(
            item["a1_candidates"]["generation_requests"] for item in selected
        ),
        "cpu_repairs": sum(
            item["a1_candidates"]["repair_source"] == "deterministic" for item in selected
        ),
        "llm_repairs": sum(item["a1_candidates"]["repair_source"] == "model" for item in selected),
        "limitation": "Single-database execution labels do not prove semantic equivalence; "
        "the pool includes deterministic edits and is not a model-only oracle.",
    }
