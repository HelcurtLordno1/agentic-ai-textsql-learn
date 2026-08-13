"""Gold-aware reporting that runs only after inference has stopped."""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from agentic_text2sql.contracts.sql import DirectStatus
from agentic_text2sql_eval.inference_runner import SmokeCase, SmokePrediction


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _gold_rows(connection: sqlite3.Connection, sql: str) -> list[list[Any]]:
    return [list(row) for row in connection.execute(sql).fetchall()]


def evaluate_predictions(
    *,
    cases: list[SmokeCase],
    predictions: list[SmokePrediction],
    database: Path,
    report_path: Path,
    evaluation_id: str = "olist-direct-p2-v1",
) -> dict[str, Any]:
    by_id = {prediction.case_id: prediction for prediction in predictions}
    details = []
    result_correct = 0
    query_cases = 0
    completed = 0
    expected_status_correct = 0
    latencies = []
    semantic_failures: dict[str, int] = {}
    prompt_tokens: list[int] = []
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        for case in cases:
            prediction = by_id[case.id]
            result = prediction.result
            typed_terminal = result.status in DirectStatus
            completed += int(typed_terminal)
            status_correct = result.status is case.expected_status
            expected_status_correct += int(status_correct)
            correct: bool | None = None
            gold_rows: list[list[Any]] | None = None
            if case.expected_status is DirectStatus.SUCCEEDED:
                query_cases += 1
                if case.gold_sql is None:
                    raise ValueError(f"Query case {case.id} has no gold SQL")
                gold_rows = _gold_rows(connection, case.gold_sql)
                correct = (
                    result.status is DirectStatus.SUCCEEDED and result.result_rows == gold_rows
                )
                result_correct += int(correct)
                if not correct:
                    for tag in case.semantic_tags or ["unclassified"]:
                        semantic_failures[tag] = semantic_failures.get(tag, 0) + 1
            total_latency = result.latency_ms.get("total", sum(result.latency_ms.values()))
            latencies.append(total_latency)
            if result.candidate is not None:
                prompt_tokens.append(result.candidate.prompt_estimated_tokens)
            details.append(
                {
                    "id": case.id,
                    "status": result.status.value,
                    "expected_status": case.expected_status.value,
                    "status_correct": status_correct,
                    "result_correct": correct,
                    "generated_sql": (
                        result.candidate.normalized_sql if result.candidate is not None else None
                    ),
                    "gold_rows": gold_rows,
                    "actual_rows": result.result_rows,
                    "error_class": result.error_class,
                    "safe_message": result.safe_message,
                    "latency_ms": result.latency_ms,
                    "semantic_tags": case.semantic_tags,
                    "correction": result.correction,
                }
            )
    finally:
        connection.close()
    report: dict[str, Any] = {
        "evaluation_id": evaluation_id,
        "case_count": len(cases),
        "typed_terminal_count": completed,
        "workflow_completion_rate": completed / len(cases),
        "expected_status_correct_count": expected_status_correct,
        "expected_status_accuracy": expected_status_correct / len(cases),
        "query_case_count": query_cases,
        "result_correct_count": result_correct,
        "result_accuracy": result_correct / query_cases if query_cases else 0.0,
        "latency_ms": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
        },
        "prompt_estimated_tokens": {
            "average": sum(prompt_tokens) / len(prompt_tokens) if prompt_tokens else 0.0,
            "maximum": max(prompt_tokens, default=0),
        },
        "semantic_failures": semantic_failures,
        "correction": _correction_metrics(details),
        "details": details,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report


def _correction_metrics(details: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = [item["correction"] for item in details if item.get("correction") is not None]
    attempted = [item for item in outcomes if item["attempted"]]
    recovered = [item for item in attempted if item["recovered"]]
    categories: dict[str, dict[str, int]] = {}
    stop_reasons: dict[str, int] = {}
    for outcome in outcomes:
        reason = str(outcome["stop_reason"])
        stop_reasons[reason] = stop_reasons.get(reason, 0) + 1
        category = outcome.get("trigger_error_class")
        if category:
            bucket = categories.setdefault(category, {"attempted": 0, "recovered": 0})
            bucket["attempted"] += 1
            bucket["recovered"] += int(bool(outcome["recovered"]))
    return {
        "attempted_count": len(attempted),
        "recovered_count": len(recovered),
        "recovery_rate": len(recovered) / len(attempted) if attempted else 0.0,
        "total_repairs": sum(int(item["repairs"]) for item in outcomes),
        "total_llm_calls": sum(int(item["llm_calls"]) for item in outcomes),
        "stop_reasons": stop_reasons,
        "by_final_category": categories,
    }
