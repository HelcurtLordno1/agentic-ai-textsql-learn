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
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql_eval.din_sql_metrics import aggregate_plan_metrics, evaluate_plan
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
    expected_rows_cache: dict[str, list[list[Any]]] | None = None,
) -> dict[str, Any]:
    """Evaluate gold-blind predictions, optionally reusing evaluator-only expected rows."""
    by_id = {prediction.case_id: prediction for prediction in predictions}
    if set(by_id) != {case.id for case in cases}:
        raise ValueError("Predictions must match the complete acceptance manifest")
    details: list[dict[str, Any]] = []
    shadow_details: list[dict[str, Any]] = []
    din_metrics: list[dict[str, Any]] = []
    latencies: list[float] = []
    catalog = SQLiteIntrospector().inspect(database, "olist")
    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    expected_rows_cache = expected_rows_cache if expected_rows_cache is not None else {}
    try:
        connection.execute("PRAGMA query_only=ON")
        for case in cases:
            result = by_id[case.id].result
            expected_rows = expected_rows_cache.get(case.id)
            if expected_rows is None:
                expected_rows = [list(row) for row in connection.execute(case.gold_sql).fetchall()]
                expected_rows_cache[case.id] = expected_rows
            correct = result.status is DirectStatus.SUCCEEDED and _rows_equal(
                result.result_rows,
                expected_rows,
                order_matters=case.result_order_matters,
                tolerance=case.tolerance,
            )
            arbitration = result.arbitration
            if arbitration is not None:
                incumbent_correct = (
                    arbitration.incumbent_status is DirectStatus.SUCCEEDED
                    and _rows_equal(
                        arbitration.incumbent_result_rows,
                        expected_rows,
                        order_matters=case.result_order_matters,
                        tolerance=case.tolerance,
                    )
                )
                challenger_observed = arbitration.challenger_status is not None
                challenger_available = arbitration.challenger_proof_accepted
                challenger_correct = bool(
                    arbitration.challenger_status is DirectStatus.SUCCEEDED
                    and _rows_equal(
                        arbitration.challenger_result_rows,
                        expected_rows,
                        order_matters=case.result_order_matters,
                        tolerance=case.tolerance,
                    )
                )
                shadow_details.append(
                    {
                        "id": case.id,
                        "partition": case.partition,
                        "selection": arbitration.selection.value,
                        "reason": arbitration.reason,
                        "incumbent_status": arbitration.incumbent_status.value,
                        "challenger_status": (
                            arbitration.challenger_status.value
                            if arbitration.challenger_status is not None
                            else None
                        ),
                        "challenger_observed": challenger_observed,
                        "incumbent_correct": incumbent_correct,
                        "challenger_available": challenger_available,
                        "challenger_correct": challenger_correct,
                        "proof_kind": arbitration.challenger_proof_kind,
                        "rule_ids": arbitration.challenger_rule_ids,
                        "incumbent_fingerprint": arbitration.incumbent_fingerprint,
                        "challenger_fingerprint": arbitration.challenger_fingerprint,
                        "challenger_contradictions": arbitration.challenger_contradictions,
                    }
                )
            total_latency = result.latency_ms.get("total", sum(result.latency_ms.values()))
            latencies.append(total_latency)
            generated_sql = (
                result.candidate.normalized_sql if result.candidate is not None else None
            )
            din_metric = None
            if result.plan is not None and "clauses" in result.plan:
                din_metric = evaluate_plan(
                    result.plan,
                    gold_sql=case.gold_sql,
                    predicted_sql=generated_sql,
                    catalog=catalog,
                )
                din_metrics.append(din_metric)
            details.append(
                {
                    "id": case.id,
                    "partition": case.partition,
                    "language": case.language,
                    "difficulty": case.difficulty,
                    "status": result.status.value,
                    "result_correct": correct,
                    "generated_sql": generated_sql,
                    "expected_result_hash": hashlib.sha256(
                        repr(expected_rows).encode()
                    ).hexdigest(),
                    "actual_rows": result.result_rows,
                    "latency_ms": result.latency_ms,
                    "required_concepts": case.required_concepts,
                    "error_class": result.error_class,
                    "plan_validation": result.plan_validation,
                    "din_sql_plan_metrics": din_metric,
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
    paired_shadow = [item for item in shadow_details if item["challenger_available"]]
    proof_kinds = sorted(
        {str(item["proof_kind"]) for item in paired_shadow if item["proof_kind"] is not None}
    )

    def proof_kind_metrics(proof_kind: str) -> dict[str, int | float]:
        selected = [item for item in paired_shadow if item["proof_kind"] == proof_kind]
        challenger_correct = sum(bool(item["challenger_correct"]) for item in selected)
        regressions = sum(
            bool(item["incumbent_correct"]) and not bool(item["challenger_correct"])
            for item in selected
        )
        improvements = sum(
            not bool(item["incumbent_correct"]) and bool(item["challenger_correct"])
            for item in selected
        )
        return {
            "count": len(selected),
            "challenger_correct": challenger_correct,
            "challenger_accuracy": challenger_correct / len(selected),
            "improvements": improvements,
            "regressions": regressions,
            "net_change": improvements - regressions,
        }

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
        "din_sql_planning": aggregate_plan_metrics(din_metrics),
        "candidate_shadow": {
            "case_count": len(shadow_details),
            "paired_count": len(paired_shadow),
            "skipped_count": len(shadow_details) - len(paired_shadow),
            "improvements": sum(
                not bool(item["incumbent_correct"]) and bool(item["challenger_correct"])
                for item in paired_shadow
            ),
            "regressions": sum(
                bool(item["incumbent_correct"]) and not bool(item["challenger_correct"])
                for item in paired_shadow
            ),
            "both_correct": sum(
                bool(item["incumbent_correct"]) and bool(item["challenger_correct"])
                for item in paired_shadow
            ),
            "both_wrong": sum(
                not bool(item["incumbent_correct"]) and not bool(item["challenger_correct"])
                for item in paired_shadow
            ),
            "by_proof_kind": {
                proof_kind: proof_kind_metrics(proof_kind) for proof_kind in proof_kinds
            },
            "details": shadow_details,
        },
        "details": details,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_suffix(f"{report_path.suffix}.tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(report_path)
    return report
