"""Guarded sparse recovery for an interrupted Olist run after architecture changes.

This is deliberately labelled adaptive recovery rather than a fresh blind benchmark. Correct
source predictions are immutable seeds; only observed failures and never-run cases are inferred.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from agentic_text2sql.settings import Settings
from agentic_text2sql_eval.inference_runner import SmokePrediction
from agentic_text2sql_eval.olist_acceptance import (
    OlistAcceptanceCase,
    evaluate_olist_acceptance,
    load_olist_acceptance,
)
from scripts.run_guarded_acceptance import stage_runtime_inputs
from scripts.run_r2_olist_research import (
    count_lines,
    ensure_provenance,
    guarded_command,
    run_phase,
    source_digest,
    stop_lock_message,
    write_pipeline_status,
)

_EVALUATION_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prediction_lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _predictions(path: Path) -> list[SmokePrediction]:
    return [SmokePrediction.model_validate_json(line) for line in _prediction_lines(path)]


def resolve_source_artifacts(
    artifacts: Path,
    source_evaluation_id: str,
) -> tuple[Path, Path, Path]:
    """Resolve either an interrupted enforcement run or a complete recovery result."""
    predictions_dir = artifacts / "predictions"
    reports_dir = artifacts / "reports"
    interrupted = (
        predictions_dir / f"{source_evaluation_id}-enforce-olist60.jsonl",
        reports_dir / f"{source_evaluation_id}.certification.json",
        reports_dir / f"{source_evaluation_id}-enforce-olist60.progress.json",
    )
    if all(path.is_file() for path in interrupted):
        return interrupted

    combined_predictions = predictions_dir / f"{source_evaluation_id}-combined-olist60.jsonl"
    combined_report = reports_dir / f"{source_evaluation_id}-combined-olist60.json"
    provenance = reports_dir / f"{source_evaluation_id}.provenance.json"
    if not all(path.is_file() for path in (combined_predictions, combined_report, provenance)):
        raise SystemExit(
            "SOURCE_SEED_MISSING: interrupted or combined predictions/report not found"
        )
    provenance_payload = json.loads(provenance.read_text(encoding="utf-8"))
    certification_id = provenance_payload.get("source_evaluation_id")
    if not isinstance(certification_id, str) or not certification_id:
        raise SystemExit("SOURCE_PROVENANCE_INVALID: certification source is missing")
    certification = reports_dir / f"{certification_id}.certification.json"
    if not certification.is_file():
        raise SystemExit("SOURCE_SEED_MISSING: inherited certification not found")
    return combined_predictions, certification, combined_report


def audit_source_seed(
    *,
    source_predictions: Path,
    cases: list[OlistAcceptanceCase],
    database: Path,
    audit_report: Path,
    evaluation_id: str,
    source_report: Path | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, str]]:
    """Return frozen-correct IDs, sparse recovery IDs, and immutable line hashes."""
    lines = _prediction_lines(source_predictions)
    predictions = [SmokePrediction.model_validate_json(line) for line in lines]
    source_cases = cases[: len(predictions)]
    if [prediction.case_id for prediction in predictions] != [case.id for case in source_cases]:
        raise SystemExit("SOURCE_SEED_INVALID: source predictions are not a manifest prefix")
    if not predictions or len(predictions) > len(cases):
        raise SystemExit("SOURCE_SEED_INVALID: expected a non-empty manifest prefix")
    if source_report is None:
        report = evaluate_olist_acceptance(
            cases=source_cases,
            predictions=predictions,
            database=database,
            report_path=audit_report,
            evaluation_id=f"{evaluation_id}-source-seed-audit",
        )
    else:
        report = json.loads(source_report.read_text(encoding="utf-8"))
        details = report.get("details")
        if not isinstance(details, list) or len(details) != len(predictions):
            raise SystemExit("SOURCE_REPORT_INVALID: detail count does not match predictions")
        by_id = {prediction.case_id: prediction for prediction in predictions}
        for detail in details:
            if not isinstance(detail, dict) or str(detail.get("id")) not in by_id:
                raise SystemExit("SOURCE_REPORT_INVALID: detail IDs do not match predictions")
            prediction = by_id[str(detail["id"])]
            result = prediction.result
            generated_sql = (
                result.candidate.normalized_sql if result.candidate is not None else None
            )
            if (
                detail.get("status") != result.status.value
                or detail.get("actual_rows") != result.result_rows
                or detail.get("generated_sql") != generated_sql
            ):
                raise SystemExit(
                    f"SOURCE_REPORT_MISMATCH: report does not describe {prediction.case_id}"
                )
        audit_payload = {
            **report,
            "evaluation_id": f"{evaluation_id}-source-seed-audit",
            "reused_source_report": str(source_report),
        }
        audit_report.parent.mkdir(parents=True, exist_ok=True)
        temporary = audit_report.with_suffix(f"{audit_report.suffix}.tmp")
        temporary.write_text(
            json.dumps(audit_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        temporary.replace(audit_report)
    correct_ids = tuple(
        str(detail["id"]) for detail in report["details"] if detail["result_correct"]
    )
    correct = set(correct_ids)
    recovery_ids = tuple(case.id for case in cases if case.id not in correct)
    line_hashes = {
        prediction.case_id: hashlib.sha256(line.encode("utf-8")).hexdigest()
        for prediction, line in zip(predictions, lines, strict=True)
        if prediction.case_id in correct
    }
    return correct_ids, recovery_ids, line_hashes


def merge_predictions(
    *,
    cases: list[OlistAcceptanceCase],
    source_predictions: Path,
    recovery_predictions: Path,
    preserved_hashes: dict[str, str],
    destination: Path,
) -> list[SmokePrediction]:
    """Merge by case ID while proving that every preserved source line stayed byte-identical."""
    source_lines = _prediction_lines(source_predictions)
    recovery_lines = _prediction_lines(recovery_predictions)
    by_id: dict[str, str] = {}
    for line in source_lines:
        prediction = SmokePrediction.model_validate_json(line)
        expected = preserved_hashes.get(prediction.case_id)
        if expected is None:
            continue
        if hashlib.sha256(line.encode("utf-8")).hexdigest() != expected:
            raise SystemExit(f"PRESERVED_SEED_CHANGED: {prediction.case_id}")
        by_id[prediction.case_id] = line
    for line in recovery_lines:
        prediction = SmokePrediction.model_validate_json(line)
        if prediction.case_id in by_id:
            raise SystemExit(f"RECOVERY_OVERWROTE_PRESERVED_SUCCESS: {prediction.case_id}")
        by_id[prediction.case_id] = line
    expected_ids = [case.id for case in cases]
    if set(by_id) != set(expected_ids):
        missing = sorted(set(expected_ids) - set(by_id))
        extra = sorted(set(by_id) - set(expected_ids))
        raise SystemExit(f"RECOVERY_MERGE_INCOMPLETE: missing={missing}; extra={extra}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    temporary.write_text(
        "\n".join(by_id[case_id] for case_id in expected_ids) + "\n", encoding="utf-8"
    )
    temporary.replace(destination)
    return _predictions(destination)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation-id", required=True)
    parser.add_argument("--source-evaluation-id", required=True)
    parser.add_argument("--skip-check", action="store_true")
    args = parser.parse_args()
    for value in (args.evaluation_id, args.source_evaluation_id):
        if _EVALUATION_ID.fullmatch(value) is None:
            raise SystemExit("evaluation IDs must be 3-80 lowercase safe characters")
    if args.evaluation_id == args.source_evaluation_id:
        raise SystemExit("recovery requires a fresh evaluation ID")

    root = Path(__file__).resolve().parents[1]
    artifacts = root / "evals"
    source_predictions, source_certification, source_progress = resolve_source_artifacts(
        artifacts,
        args.source_evaluation_id,
    )

    recovery_id = f"{args.evaluation_id}-recovery-cases"
    recovery_predictions = artifacts / "predictions" / f"{recovery_id}.jsonl"
    recovery_report = artifacts / "reports" / f"{recovery_id}.json"
    recovery_progress = artifacts / "reports" / f"{recovery_id}.progress.json"
    recovery_stop = artifacts / "reports" / f"{recovery_id}.resource-stop.json"
    if lock := stop_lock_message(recovery_stop):
        raise SystemExit(f"{lock}; review it and use a fresh evaluation ID")
    if not args.skip_check:
        subprocess.run(["make", "check"], cwd=root, check=True)

    settings = Settings()
    database = settings.resolved_data_dir / "processed/olist.sqlite"
    cases = load_olist_acceptance(root / "evals/configs/olist-acceptance-60.jsonl")
    audit_report = artifacts / "reports" / f"{args.evaluation_id}.seed-audit.json"
    preserved_ids, recovery_ids, preserved_hashes = audit_source_seed(
        source_predictions=source_predictions,
        cases=cases,
        database=database,
        audit_report=audit_report,
        evaluation_id=args.evaluation_id,
        source_report=source_progress,
    )
    certification: dict[str, Any] = json.loads(source_certification.read_text(encoding="utf-8"))
    certified = tuple(str(value) for value in certification.get("certified_proof_kinds", ()))
    required_kinds = {
        "aggregate:avg",
        "aggregate:count_rows",
        "aggregate:sum",
        "frequency_ranking",
    }
    if not required_kinds <= set(certified):
        raise SystemExit(
            "SOURCE_CERTIFICATION_INSUFFICIENT: relational operator kinds not certified"
        )

    digest = source_digest(root)
    provenance_path = artifacts / "reports" / f"{args.evaluation_id}.provenance.json"
    ensure_provenance(
        provenance_path,
        {
            "schema_version": 1,
            "evaluation_id": args.evaluation_id,
            "source_digest": digest,
            "methodology": "adaptive_recovery_not_blind",
            "source_evaluation_id": args.source_evaluation_id,
            "source_predictions_sha256": _sha256(source_predictions),
            "source_certification_sha256": _sha256(source_certification),
            "source_progress_sha256": _sha256(source_progress),
            "preserved_case_ids": list(preserved_ids),
            "preserved_prediction_line_sha256": preserved_hashes,
            "recovery_case_ids": list(recovery_ids),
            "profile": "olist-paper1-ultrasafe",
            "batch_size": 1,
            "cooldown_seconds": 60,
            "sample_seconds": 0.5,
            "batch_timeout_seconds": 360,
            "pilot_batches": 1,
        },
    )
    status_path = artifacts / "reports" / f"{args.evaluation_id}.pipeline-status.json"

    def update_status(state: str, phase: str, **detail: object) -> None:
        write_pipeline_status(
            status_path,
            {
                "schema_version": 1,
                "evaluation_id": args.evaluation_id,
                "source_digest": digest,
                "methodology": "adaptive_recovery_not_blind",
                "state": state,
                "phase": phase,
                **detail,
            },
        )

    environment = {
        **os.environ,
        "TEXT2SQL_PLANNING_MODE": "hybrid",
        "TEXT2SQL_CANDIDATE_MODE": "enforce",
        "TEXT2SQL_CERTIFIED_PROOF_KINDS": ",".join(certified),
        "TEXT2SQL_CANDIDATE_TOTAL_DEADLINE_SECONDS": "300",
        "TEXT2SQL_CANDIDATE_MINIMUM_CHALLENGER_SECONDS": "45",
    }

    def execute(command: list[str], phase: str) -> None:
        update_status(
            "running",
            phase,
            checkpoint=count_lines(recovery_predictions),
            recovery_case_count=len(recovery_ids),
            preserved_case_count=len(preserved_ids),
        )
        try:
            run_phase(
                command,
                root=root,
                environment=environment,
                phase=phase,
                predictions=recovery_predictions,
                stop_record=recovery_stop,
            )
        except SystemExit as exc:
            update_status(
                "stopped",
                phase,
                checkpoint=count_lines(recovery_predictions),
                reason=str(exc),
            )
            raise
        update_status("phase_complete", phase, checkpoint=count_lines(recovery_predictions))

    def recovery_command(*, max_batches: int | None = None) -> list[str]:
        return guarded_command(
            root,
            evaluation_id=recovery_id,
            predictions=recovery_predictions,
            report=recovery_report,
            progress=recovery_progress,
            stop_record=recovery_stop,
            case_ids=recovery_ids,
            max_batches=max_batches,
        )

    execute(recovery_command(max_batches=1), "recovery-pilot")
    execute(recovery_command(), "recovery")

    combined_predictions = (
        artifacts / "predictions" / f"{args.evaluation_id}-combined-olist60.jsonl"
    )
    combined_report = artifacts / "reports" / f"{args.evaluation_id}-combined-olist60.json"
    merged = merge_predictions(
        cases=cases,
        source_predictions=source_predictions,
        recovery_predictions=recovery_predictions,
        preserved_hashes=preserved_hashes,
        destination=combined_predictions,
    )
    with tempfile.TemporaryDirectory(prefix="agentic-text2sql-final-eval-") as temporary:
        staged_database, _, _ = stage_runtime_inputs(database, Path(temporary))
        report = evaluate_olist_acceptance(
            cases=cases,
            predictions=merged,
            database=staged_database,
            report_path=combined_report,
            evaluation_id=f"{args.evaluation_id}-combined-olist60",
        )
    report["methodology"] = "adaptive_recovery_not_blind"
    report["recovery"] = {
        "source_evaluation_id": args.source_evaluation_id,
        "preserved_case_ids": list(preserved_ids),
        "inferred_case_ids": list(recovery_ids),
        "preserved_prediction_line_sha256": preserved_hashes,
    }
    report_temporary = combined_report.with_suffix(f"{combined_report.suffix}.tmp")
    report_temporary.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    report_temporary.replace(combined_report)
    update_status(
        "complete",
        "merge",
        report=str(combined_report),
        result_correct_count=report["result_correct_count"],
        case_count=report["case_count"],
        preserved_case_count=len(preserved_ids),
        recovery_case_count=len(recovery_ids),
    )
    print(
        "R2_ADAPTIVE_RECOVERY_COMPLETE: "
        f"{report['result_correct_count']}/{report['case_count']}; "
        f"preserved={len(preserved_ids)}; inferred={len(recovery_ids)}; "
        f"report={combined_report}"
    )


if __name__ == "__main__":
    main()
