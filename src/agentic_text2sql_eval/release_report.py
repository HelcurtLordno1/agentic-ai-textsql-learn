"""Gate P6 release aggregation without blending benchmark scores."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"report is not an object: {path}")
    return payload


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_release_report(
    *,
    olist_report_path: Path,
    spider_report_path: Path,
    retrieval_ablation_path: Path,
    correction_ablation_path: Path,
) -> dict[str, Any]:
    olist = _load(olist_report_path)
    spider = _load(spider_report_path)
    if int(olist.get("case_count", 0)) != 60:
        raise ValueError("P6 requires a complete Olist-60 report")
    spider_manifest = spider.get("manifest")
    profile = (
        spider_manifest.get("benchmark_profile") if isinstance(spider_manifest, dict) else None
    )
    if (
        int(spider.get("case_count", 0)) != 200
        or profile != "laptop-stratified"
        or spider.get("release_status") != "complete"
    ):
        raise ValueError("P6 requires a complete laptop-stratified Spider-200 report")
    ablations = {
        kind: {
            "path": str(path),
            "sha256": _hash(path),
            "evaluation_id": _load(path).get("evaluation_id", path.stem),
        }
        for kind, path in {
            "retrieval": retrieval_ablation_path,
            "correction": correction_ablation_path,
        }.items()
    }
    return {
        "evaluation_id": "p6-core-release-v1",
        "release_status": "complete",
        "score_policy": "Olist and Spider remain separate; no blended accuracy is computed.",
        "olist": {
            "evaluation_id": olist.get("evaluation_id"),
            "case_count": olist["case_count"],
            "result_accuracy": olist.get("result_accuracy"),
            "workflow_completion_rate": olist.get("workflow_completion_rate"),
            "sha256": _hash(olist_report_path),
        },
        "spider": {
            "evaluation_id": spider.get("evaluation_id"),
            "case_count": spider["case_count"],
            "database_count": spider.get("database_count"),
            "benchmark_profile": profile,
            "by_partition": spider.get("by_partition"),
            "result_accuracy": spider.get("result_accuracy"),
            "workflow_completion_rate": spider.get("workflow_completion_rate"),
            "sha256": _hash(spider_report_path),
        },
        "ablations": ablations,
        "limitations": spider.get("limitations", []),
    }
