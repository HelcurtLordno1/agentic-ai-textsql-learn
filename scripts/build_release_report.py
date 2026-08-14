"""Build the gold-free aggregate Gate P6 release report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentic_text2sql_eval.release_report import build_release_report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--olist-report", type=Path, required=True)
    parser.add_argument("--spider-report", type=Path, required=True)
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--correction-ablation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_release_report(
        olist_report_path=args.olist_report,
        spider_report_path=args.spider_report,
        retrieval_ablation_path=args.retrieval_ablation,
        correction_ablation_path=args.correction_ablation,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
