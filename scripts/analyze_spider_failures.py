"""Build a gold-aware, local-only Spider failure analysis after inference has stopped."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from agentic_text2sql_eval.failure_analysis import (
    analyze_spider_failures,
    calculate_review_agreement,
    load_json_object,
    load_reviewer_labels,
    write_analysis,
)
from agentic_text2sql_eval.spider_release import load_release_cases


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spider-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--release-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--analysis-id", required=True)
    parser.add_argument("--review-a", type=Path)
    parser.add_argument("--review-b", type=Path)
    args = parser.parse_args()
    if (args.review_a is None) != (args.review_b is None):
        raise SystemExit("both --review-a and --review-b are required for agreement")

    _, cases = load_release_cases(args.spider_root, args.manifest)
    release_report = load_json_object(args.release_report)
    analysis = analyze_spider_failures(
        spider_root=args.spider_root,
        cases=cases,
        release_report=release_report,
        source_report_sha256=sha256_file(args.release_report),
        analysis_id=args.analysis_id,
    )
    write_analysis(analysis, args.output)
    summary: dict[str, object] = {
        "analysis_id": analysis.analysis_id,
        "case_count": analysis.case_count,
        "failure_count": analysis.failure_count,
        "review_required_count": analysis.review_required_count,
        "by_primary_cause": analysis.by_primary_cause,
        "output": str(args.output),
    }
    if args.review_a is not None and args.review_b is not None:
        agreement = calculate_review_agreement(
            load_reviewer_labels(args.review_a), load_reviewer_labels(args.review_b)
        )
        summary["review_agreement"] = agreement.model_dump(mode="json")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
