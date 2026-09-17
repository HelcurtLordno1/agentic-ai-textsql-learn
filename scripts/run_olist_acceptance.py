"""Run the reviewed, gold-separated Gate P5 Olist-60 acceptance suite."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from contextlib import nullcontext
from pathlib import Path

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.sql import DirectStatus
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer6_application.service_factory import RuntimeBundle
from agentic_text2sql.settings import Settings
from agentic_text2sql_eval.inference_runner import SmokeCase, SmokePrediction, run_inference
from agentic_text2sql_eval.olist_acceptance import (
    evaluate_olist_acceptance,
    load_olist_acceptance,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--evaluation-id", default="olist-acceptance-60-p5-v1")
    parser.add_argument("--correction", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-new-cases", type=int)
    parser.add_argument("--retry-last-infrastructure-error", action="store_true")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--catalog-snapshot", type=Path)
    parser.add_argument("--only-case-id", action="append", default=[])
    parser.add_argument(
        "--partition", action="append", choices=("dev", "regression", "holdout"), default=[]
    )
    args = parser.parse_args()
    settings = Settings()
    root = settings.project_root
    cases_path = args.cases or root / "evals/configs/olist-acceptance-60.jsonl"
    predictions_path = args.predictions or root / "evals/predictions/olist-p5-60.jsonl"
    report_path = args.report or root / "evals/reports/olist-p5-60.json"
    acceptance = load_olist_acceptance(cases_path)
    if args.partition:
        selected_partitions = set(args.partition)
        acceptance = [case for case in acceptance if case.partition in selected_partitions]
    if args.only_case_id:
        if args.predictions is None or args.report is None:
            raise SystemExit("filtered runs require explicit --predictions and --report paths")
        selected = set(args.only_case_id)
        known = {case.id for case in load_olist_acceptance(cases_path)}
        if unknown := selected - known:
            raise SystemExit(f"unknown case IDs: {', '.join(sorted(unknown))}")
        acceptance = [case for case in acceptance if case.id in selected]
    blind_cases = [
        SmokeCase(
            id=case.id,
            language=case.language,
            question=case.question,
            expected_status=DirectStatus.SUCCEEDED,
            semantic_tags=list(case.required_concepts),
        )
        for case in acceptance
    ]
    source_database = args.database or settings.resolved_data_dir / "processed/olist.sqlite"
    if not source_database.is_file():
        raise SystemExit(f"database not found: {source_database}")
    if args.catalog_snapshot is not None and not args.catalog_snapshot.is_file():
        raise SystemExit(f"catalog snapshot not found: {args.catalog_snapshot}")
    existing = []
    if args.resume and predictions_path.is_file():
        existing = [
            SmokePrediction.model_validate_json(line)
            for line in predictions_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if args.retry_last_infrastructure_error and existing:
            last = existing[-1].result
            retryable = last.status is DirectStatus.MODEL_ERROR and any(
                marker in (last.safe_message or "")
                for marker in ("ReadTimeout", "ProviderUnavailable", "request failed")
            )
            if retryable:
                removed = existing.pop()
                print(f"retrying infrastructure terminal for {removed.case_id}")
        print(f"resuming after {len(existing)}/{len(blind_cases)} persisted predictions")
    database_context = (
        nullcontext(None)
        if args.database is not None
        else tempfile.TemporaryDirectory(prefix="agentic-text2sql-p5-")
    )
    with database_context as temporary:
        if args.database is not None:
            database = source_database.resolve()
        else:
            if temporary is None:
                raise RuntimeError("temporary database directory was not created")
            database = Path(temporary) / "olist.sqlite"
            shutil.copyfile(source_database, database)
        catalog = (
            CatalogSnapshot.model_validate_json(args.catalog_snapshot.read_text(encoding="utf-8"))
            if args.catalog_snapshot is not None
            else SQLiteIntrospector().inspect(database, "olist")
        )
        if catalog.db_id != "olist":
            raise SystemExit(f"catalog snapshot db_id must be olist, got {catalog.db_id}")
        with RuntimeBundle(settings, catalog, correction_enabled=args.correction) as runtime:
            try:
                predictions = run_inference(
                    cases=blind_cases,
                    service=runtime,
                    database=database,
                    catalog=catalog,
                    prediction_path=predictions_path,
                    initial_predictions=existing,
                    max_new_cases=args.max_new_cases,
                )
            except KeyboardInterrupt:
                raise SystemExit("INFERENCE_INTERRUPTED_BY_GUARD") from None
        if len(predictions) != len(acceptance):
            print(
                f"checkpointed {len(predictions)}/{len(acceptance)} predictions; "
                "evaluation waits for the complete manifest"
            )
            return
        report = evaluate_olist_acceptance(
            cases=acceptance,
            predictions=predictions,
            database=database,
            report_path=report_path,
            evaluation_id=args.evaluation_id,
        )
    print(json.dumps({key: value for key, value in report.items() if key != "details"}, indent=2))


if __name__ == "__main__":
    main()
