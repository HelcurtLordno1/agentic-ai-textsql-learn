"""Inspect saved A1 predictions only; never initialize a runtime or execute SQL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentic_text2sql_eval.a1_diagnostics import ReviewedA1Label, diagnose_a1
from agentic_text2sql_eval.inference_runner import SmokePrediction
from agentic_text2sql_eval.runtime_checkpoint import atomic_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--reviewed-labels", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    predictions = [
        SmokePrediction.model_validate_json(line)
        for line in args.predictions.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    labels = (
        []
        if args.reviewed_labels is None
        else [
            ReviewedA1Label.model_validate_json(line)
            for line in args.reviewed_labels.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    )
    report = diagnose_a1(predictions, labels)
    atomic_json(args.output, report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
