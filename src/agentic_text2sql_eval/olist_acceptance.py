"""Reviewed Olist-60 manifest contracts and offline result evaluation."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentic_text2sql.contracts.sql import DirectStatus
from agentic_text2sql_eval.inference_runner import SmokePrediction
from agentic_text2sql_eval.report import _percentile


class OlistAcceptanceCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    partition: Literal["dev", "regression", "holdout"]
    language: Literal["vi", "en"]
    question: str
    difficulty: Literal["easy", "medium", "hard"]
    required_concepts: tuple[str, ...]
    gold_sql: str
    result_order_matters: bool = False
    tolerance: float = Field(default=0.0, ge=0)
    invariants: tuple[str, ...] = ()
    reviewed: bool


def load_olist_acceptance(path: Path) -> list[OlistAcceptanceCase]:
    cases = [
        OlistAcceptanceCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(cases) != 60 or len({case.id for case in cases}) != 60:
        raise ValueError("Olist acceptance manifest must contain exactly 60 unique cases")
    if len({case.question.casefold() for case in cases}) != 60:
        raise ValueError("Olist acceptance questions must be unique")
    if len({" ".join(case.gold_sql.split()).casefold() for case in cases}) != 60:
        raise ValueError("Olist acceptance gold queries must be unique across partitions")
    expected = {"dev": 30, "regression": 15, "holdout": 15}
    actual = {key: sum(case.partition == key for case in cases) for key in expected}
    if actual != expected:
        raise ValueError(f"Invalid Olist partition sizes: {actual}")
    if not all(case.reviewed for case in cases):
        raise ValueError("Every Olist acceptance case must be reviewed")
    return cases


def validate_gold_queries(cases: list[OlistAcceptanceCase], database: Path) -> dict[str, str]:
    """Execute reviewed gold only in the evaluator and return result hashes."""
    hashes: dict[str, str] = {}
    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        for case in cases:
            rows = connection.execute(case.gold_sql).fetchall()
            canonical = repr(rows).encode()
            hashes[case.id] = hashlib.sha256(canonical).hexdigest()
    finally:
        connection.close()
    return hashes


def _value_equal(actual: Any, expected: Any, tolerance: float) -> bool:
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=0, abs_tol=tolerance)
    return bool(actual == expected)


def _rows_equal(
    actual: list[list[Any]],
    expected: list[list[Any]],
    *,
    order_matters: bool,
    tolerance: float,
) -> bool:
    if not order_matters:
        actual = sorted(actual, key=repr)
        expected = sorted(expected, key=repr)
    return len(actual) == len(expected) and all(
        len(actual_row) == len(expected_row)
        and all(
            _value_equal(actual_value, expected_value, tolerance)
            for actual_value, expected_value in zip(actual_row, expected_row, strict=True)
        )
        for actual_row, expected_row in zip(actual, expected, strict=True)
    )


def evaluate_olist_acceptance(
    *,
    cases: list[OlistAcceptanceCase],
    predictions: list[SmokePrediction],
    database: Path,
    report_path: Path,
    evaluation_id: str = "olist-acceptance-60-p5-v1",
) -> dict[str, Any]:
    """Evaluate gold-blind predictions after inference has completely stopped."""
    by_id = {prediction.case_id: prediction for prediction in predictions}
    if set(by_id) != {case.id for case in cases}:
        raise ValueError("Predictions must match the complete acceptance manifest")
    details: list[dict[str, Any]] = []
    latencies: list[float] = []
    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        for case in cases:
            result = by_id[case.id].result
            expected_rows = [list(row) for row in connection.execute(case.gold_sql).fetchall()]
            correct = result.status is DirectStatus.SUCCEEDED and _rows_equal(
                result.result_rows,
                expected_rows,
                order_matters=case.result_order_matters,
                tolerance=case.tolerance,
            )
            total_latency = result.latency_ms.get("total", sum(result.latency_ms.values()))
            latencies.append(total_latency)
            details.append(
                {
                    "id": case.id,
                    "partition": case.partition,
                    "language": case.language,
                    "difficulty": case.difficulty,
                    "status": result.status.value,
                    "result_correct": correct,
                    "generated_sql": (
                        result.candidate.normalized_sql if result.candidate is not None else None
                    ),
                    "expected_result_hash": hashlib.sha256(
                        repr(expected_rows).encode()
                    ).hexdigest(),
                    "actual_rows": result.result_rows,
                    "latency_ms": result.latency_ms,
                    "required_concepts": case.required_concepts,
                    "error_class": result.error_class,
                    "correction": result.correction,
                }
            )
    finally:
        connection.close()

    correct_count = sum(bool(item["result_correct"]) for item in details)
    correction_attempts = [
        item for item in details if bool((item.get("correction") or {}).get("attempted"))
    ]
    correction_recovered = [
        item for item in correction_attempts if bool(item["correction"].get("recovered"))
    ]
    candidate_count = sum(item["generated_sql"] is not None for item in details)
    first_pass_correct = sum(
        bool(item["result_correct"]) and not bool((item.get("correction") or {}).get("attempted"))
        for item in details
    )

    def slice_metrics(field: str) -> dict[str, dict[str, float | int]]:
        values = sorted({str(item[field]) for item in details})
        result: dict[str, dict[str, float | int]] = {}
        for value in values:
            selected = [item for item in details if item[field] == value]
            selected_correct = sum(bool(item["result_correct"]) for item in selected)
            result[value] = {
                "count": len(selected),
                "correct": selected_correct,
                "accuracy": selected_correct / len(selected),
            }
        return result

    report: dict[str, Any] = {
        "evaluation_id": evaluation_id,
        "case_count": len(cases),
        "typed_terminal_count": sum(
            item["status"] in {status.value for status in DirectStatus} for item in details
        ),
        "workflow_completion_rate": 1.0,
        "result_correct_count": correct_count,
        "result_accuracy": correct_count / len(cases),
        "valid_candidate_count": candidate_count,
        "valid_candidate_rate": candidate_count / len(cases),
        "first_pass_correct_count": first_pass_correct,
        "first_pass_correct_rate": first_pass_correct / len(cases),
        "correction": {
            "attempted_count": len(correction_attempts),
            "recovered_count": len(correction_recovered),
            "recovery_rate": (
                len(correction_recovered) / len(correction_attempts) if correction_attempts else 0.0
            ),
        },
        "latency_ms": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
        },
        "by_partition": slice_metrics("partition"),
        "by_language": slice_metrics("language"),
        "by_difficulty": slice_metrics("difficulty"),
        "details": details,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_suffix(f"{report_path.suffix}.tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(report_path)
    return report
