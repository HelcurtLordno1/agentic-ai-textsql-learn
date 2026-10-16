"""Offline saved-artifact inventory; observations are not reviewed root causes."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def audit_saved_runs(
    control_report: Path, treatment_report: Path, predictions: Path
) -> dict[str, Any]:
    control = json.loads(control_report.read_text(encoding="utf-8"))
    treatment = json.loads(treatment_report.read_text(encoding="utf-8"))
    rows = [
        json.loads(line) for line in predictions.read_text(encoding="utf-8").splitlines() if line
    ]

    def keyed(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
        result = {item[key]: item for item in items}
        if len(result) != len(items):
            raise ValueError("duplicate case identifiers")
        return result

    left = keyed(control["details"], "id")
    right = keyed(treatment["details"], "id")
    traces = keyed(rows, "case_id")
    if not left or left.keys() != right.keys() or left.keys() != traces.keys():
        raise ValueError("audit requires matching complete case sets")
    paired: Counter[str] = Counter()
    observations: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    for identifier in sorted(left):
        a, b = left[identifier], right[identifier]
        if a["db_id"] != b["db_id"]:
            raise ValueError("database identity mismatch")
        group = (
            "both_correct"
            if a["result_correct"] and b["result_correct"]
            else "control_only"
            if a["result_correct"]
            else "treatment_only"
            if b["result_correct"]
            else "both_wrong"
        )
        paired[group] += 1
        result = traces[identifier]["result"]
        if a.get("generated_sql") != (result.get("candidate") or {}).get("normalized_sql"):
            raise ValueError("control report SQL does not match its saved prediction")
        present = {
            name: result.get(name) is not None for name in ("plan", "schema_context", "candidate")
        }
        for name, available in present.items():
            observations[f"{name}_present"] += available
            if not a["result_correct"]:
                observations[f"failure_{name}_present"] += available
        records.append(
            {
                "case_id": identifier,
                "db_id": a["db_id"],
                "paired_group": group,
                "exposure_status": "exposed_development",
                "status": result["status"],
                "saved_evidence": present,
                "actual_prompt_available": False,
                "first_pass_available": not bool((result.get("correction") or {}).get("attempted")),
                "review_status": "UNREVIEWED",
                "semantic_error_family": "UNKNOWN",
                "originating_component": "UNKNOWN",
                "unresolved_reason": "Saved artifacts cannot establish intent or root cause",
            }
        )
    return {
        "audit_version": "e0-inventory-v1",
        "case_count": len(left),
        "paired": dict(sorted(paired.items())),
        "observations": dict(sorted(observations.items())),
        "input_sha256": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (control_report, treatment_report, predictions)
        },
        "limitations": [
            "No new inference or gold execution; report correctness labels are historical",
            "AST differences and missing traces are not causal diagnoses",
            "Rendered prompts, independent intent review and full root-cause audit remain missing",
        ],
        "records": records,
    }
