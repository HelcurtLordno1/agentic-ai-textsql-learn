"""Create an offline proof-class certification artifact from a shadow report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agentic_text2sql_eval.shadow_certification import certify_shadow_proofs, write_certification


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-cases", type=int, default=5)
    parser.add_argument("--minimum-accuracy", type=float, default=1.0)
    parser.add_argument("--minimum-improvements", type=int, default=1)
    args = parser.parse_args()
    report: dict[str, Any] = json.loads(args.report.read_text(encoding="utf-8"))
    certification = certify_shadow_proofs(
        report,
        minimum_cases=args.minimum_cases,
        minimum_accuracy=args.minimum_accuracy,
        minimum_improvements=args.minimum_improvements,
    )
    write_certification(certification, args.output)
    print(json.dumps(certification, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
