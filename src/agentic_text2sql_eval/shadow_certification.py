"""Offline-only certification of proof kinds from gold-scored shadow predictions."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def certify_shadow_proofs(
    report: dict[str, Any],
    *,
    allowed_partitions: frozenset[str] = frozenset({"dev", "regression"}),
    minimum_cases: int = 5,
    minimum_proof_kinds: int = 3,
    minimum_accuracy: float = 1.0,
    minimum_improvements: int = 1,
) -> dict[str, Any]:
    """Certify only high-precision structural classes; never individual rules or case IDs."""
    if minimum_cases < 1 or minimum_proof_kinds < 1 or minimum_improvements < 1:
        raise ValueError("certification counts must be positive")
    if not 0 < minimum_accuracy <= 1:
        raise ValueError("minimum_accuracy must be in (0, 1]")
    shadow = report.get("candidate_shadow")
    if not isinstance(shadow, dict) or not isinstance(shadow.get("details"), list):
        raise ValueError("report does not contain candidate shadow details")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in shadow["details"]:
        if not isinstance(raw, dict) or raw.get("partition") not in allowed_partitions:
            continue
        proof_kind = raw.get("proof_kind")
        if isinstance(proof_kind, str) and raw.get("challenger_available") is True:
            grouped[proof_kind].append(raw)

    metrics: dict[str, dict[str, int | float | bool]] = {}
    for proof_kind, rows in sorted(grouped.items()):
        correct = sum(bool(row.get("challenger_correct")) for row in rows)
        improvements = sum(
            not bool(row.get("incumbent_correct")) and bool(row.get("challenger_correct"))
            for row in rows
        )
        regressions = sum(
            bool(row.get("incumbent_correct")) and not bool(row.get("challenger_correct"))
            for row in rows
        )
        accuracy = correct / len(rows)
        metrics[proof_kind] = {
            "count": len(rows),
            "challenger_correct": correct,
            "accuracy": accuracy,
            "improvements": improvements,
            "regressions": regressions,
            "certified": False,
        }
    family_rows = [row for rows in grouped.values() for row in rows]
    family_correct = sum(bool(row.get("challenger_correct")) for row in family_rows)
    family_improvements = sum(
        not bool(row.get("incumbent_correct")) and bool(row.get("challenger_correct"))
        for row in family_rows
    )
    family_regressions = sum(
        bool(row.get("incumbent_correct")) and not bool(row.get("challenger_correct"))
        for row in family_rows
    )
    family_accuracy = family_correct / len(family_rows) if family_rows else 0.0
    family_certified = bool(
        len(family_rows) >= minimum_cases
        and len(grouped) >= minimum_proof_kinds
        and family_accuracy >= minimum_accuracy
        and family_improvements >= minimum_improvements
        and family_regressions == 0
    )
    certified = sorted(
        proof_kind
        for proof_kind, proof_metrics in metrics.items()
        if family_certified
        and proof_metrics["accuracy"] >= minimum_accuracy
        and proof_metrics["regressions"] == 0
    )
    for proof_kind in certified:
        metrics[proof_kind]["certified"] = True

    return {
        "schema_version": 2,
        "source_evaluation_id": report.get("evaluation_id"),
        "allowed_partitions": sorted(allowed_partitions),
        "thresholds": {
            "minimum_cases": minimum_cases,
            "minimum_proof_kinds": minimum_proof_kinds,
            "minimum_accuracy": minimum_accuracy,
            "minimum_improvements": minimum_improvements,
            "maximum_regressions": 0,
        },
        "certified_proof_kinds": certified,
        "proof_family": {
            "name": "catalog_proven_typed_compiler_v1",
            "count": len(family_rows),
            "proof_kind_count": len(grouped),
            "challenger_correct": family_correct,
            "accuracy": family_accuracy,
            "improvements": family_improvements,
            "regressions": family_regressions,
            "certified": family_certified,
        },
        "metrics": metrics,
    }


def write_certification(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
