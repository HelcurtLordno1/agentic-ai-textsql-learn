"""Export a small, gold-free Gate P6 report summary for portfolio/demo use."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ALLOWED_FIELDS = {
    "evaluation_id",
    "benchmark_kind",
    "release_status",
    "case_count",
    "database_count",
    "workflow_completion_rate",
    "result_correct_count",
    "result_accuracy",
    "valid_candidate_count",
    "latency_ms",
    "by_complexity",
    "failure_categories",
    "manifest",
    "provenance",
    "limitations",
}


def sanitize_report(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("release_status") != "complete":
        raise ValueError("only a complete release report may be exported")
    if int(payload.get("case_count", 0)) < 1:
        raise ValueError("release report has no cases")
    return {key: payload[key] for key in ALLOWED_FIELDS if key in payload}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.report.read_text(encoding="utf-8"))
    summary = sanitize_report(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"exported={args.output} fields={len(summary)}")


if __name__ == "__main__":
    main()
