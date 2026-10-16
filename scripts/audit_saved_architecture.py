"""Inventory historical artifacts without loading a local model."""

import argparse
import json
from pathlib import Path

from agentic_text2sql_eval.architecture_audit import audit_saved_runs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-report", type=Path, required=True)
    parser.add_argument("--treatment-report", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if not output.is_relative_to(root / "data/artifacts"):
        raise SystemExit("Case-level audits must stay in ignored data/artifacts")
    audit = audit_saved_runs(args.control_report, args.treatment_report, args.predictions)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in audit.items() if key != "records"}, indent=2))


if __name__ == "__main__":
    main()
