"""One-command guarded R2 shadow certification and source-locked Olist evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from agentic_text2sql_eval.shadow_certification import certify_shadow_proofs, write_certification

_EVALUATION_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")


def source_digest(root: Path) -> str:
    """Hash runtime, evaluation code, prompts and manifests without generated data."""
    roots = (
        root / "src",
        root / "configs",
        root / "datasets/olist",
        root / "evals/configs/olist-acceptance-60.jsonl",
        root / "scripts/run_guarded_acceptance.py",
        root / "scripts/run_olist_acceptance.py",
        root / "scripts/run_r2_olist_research.py",
        root / "scripts/run_r2_olist_recovery.py",
        root / "scripts/serve_ollama_guarded.py",
        root / "scripts/launch_r2_olist_tmux.py",
        root / "scripts/certify_shadow_proofs.py",
    )
    files: list[Path] = []
    for item in roots:
        if item.is_dir():
            files.extend(
                path
                for path in item.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix in {".py", ".yaml", ".yml", ".j2", ".json", ".jsonl"}
            )
        else:
            files.append(item)
    digest = hashlib.sha256()
    for path in sorted(files):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def ensure_provenance(path: Path, payload: dict[str, Any]) -> None:
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != payload:
            raise SystemExit(
                "SOURCE_LOCK_MISMATCH: use a new evaluation ID after code/config changes"
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_pipeline_status(path: Path, payload: dict[str, Any]) -> None:
    """Atomically expose the current terminal or running phase to detached operators."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def guarded_command(
    root: Path,
    *,
    evaluation_id: str,
    predictions: Path,
    report: Path,
    progress: Path,
    stop_record: Path | None = None,
    partitions: tuple[str, ...] = (),
    case_ids: tuple[str, ...] = (),
    minimum_correct: int | None = None,
    max_batches: int | None = None,
) -> list[str]:
    command = [
        "uv",
        "run",
        "python",
        str(root / "scripts/run_guarded_acceptance.py"),
        "--profile",
        "olist-paper1-ultrasafe",
        "--batch-size",
        "1",
        "--cooldown-seconds",
        "60",
        "--sample-seconds",
        "0.5",
        "--batch-timeout-seconds",
        "360",
        "--evaluation-id",
        evaluation_id,
        "--predictions",
        str(predictions),
        "--report",
        str(report),
        "--progress-report",
        str(progress),
    ]
    if stop_record is not None:
        command.extend(("--stop-record", str(stop_record)))
    for partition in partitions:
        command.extend(("--partition", partition))
    for case_id in case_ids:
        command.extend(("--only-case-id", case_id))
    if minimum_correct is not None:
        command.extend(("--minimum-correct", str(minimum_correct)))
    if max_batches is not None:
        command.extend(("--max-batches", str(max_batches)))
    return command


def stop_lock_message(path: Path) -> str | None:
    """Return a stable operator-facing lock summary without mutating the incident."""
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        reason = str(payload.get("reason", "unknown reason"))
        checkpoint = payload.get("checkpoint", "unknown")
        total = payload.get("total_cases", "unknown")
    except (OSError, ValueError, TypeError):
        return f"RESOURCE_STOP_LOCKED: {path} (unreadable incident record)"
    return f"RESOURCE_STOP_LOCKED: {path}; reason={reason}; checkpoint={checkpoint}/{total}"


def count_lines(path: Path) -> int:
    return (
        sum(bool(line.strip()) for line in path.read_text(encoding="utf-8").splitlines())
        if path.is_file()
        else 0
    )


def run_phase(
    command: list[str],
    *,
    root: Path,
    environment: dict[str, str],
    phase: str,
    predictions: Path,
    stop_record: Path,
) -> None:
    """Run one guarded phase and convert child exits into concise checkpoint diagnostics."""
    try:
        subprocess.run(command, cwd=root, env=environment, check=True)
    except subprocess.CalledProcessError as exc:
        checkpoint = count_lines(predictions)
        lock = stop_lock_message(stop_record)
        detail = lock or f"inspect guarded output and {predictions}"
        raise SystemExit(
            f"R2_PHASE_STOPPED: phase={phase}; exit_code={exc.returncode}; "
            f"checkpoint={checkpoint}; {detail}"
        ) from None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation-id", required=True)
    parser.add_argument("--skip-check", action="store_true")
    args = parser.parse_args()
    if _EVALUATION_ID.fullmatch(args.evaluation_id) is None:
        raise SystemExit("evaluation-id must be 3-80 lowercase safe characters")

    root = Path(__file__).resolve().parents[1]
    artifact_root = root / "evals"
    shadow_id = f"{args.evaluation_id}-shadow-dev-regression"
    enforce_id = f"{args.evaluation_id}-enforce-olist60"
    shadow_stop_record = artifact_root / "reports" / f"{shadow_id}.resource-stop.json"
    enforce_stop_record = artifact_root / "reports" / f"{enforce_id}.resource-stop.json"
    for stop_record in (shadow_stop_record, enforce_stop_record):
        if lock := stop_lock_message(stop_record):
            raise SystemExit(f"{lock}; review it and use a fresh evaluation ID")
    if not args.skip_check:
        subprocess.run(["make", "check"], cwd=root, check=True)
    digest = source_digest(root)
    provenance_path = artifact_root / "reports" / f"{args.evaluation_id}.provenance.json"
    ensure_provenance(
        provenance_path,
        {
            "schema_version": 1,
            "evaluation_id": args.evaluation_id,
            "source_digest": digest,
            "profile": "olist-paper1-ultrasafe",
            "batch_size": 1,
            "cooldown_seconds": 60,
            "sample_seconds": 0.5,
            "batch_timeout_seconds": 360,
            "pilot_batches_per_phase": 1,
            "promotion_target": 58,
        },
    )
    status_path = artifact_root / "reports" / f"{args.evaluation_id}.pipeline-status.json"

    def update_status(state: str, phase: str, **detail: object) -> None:
        write_pipeline_status(
            status_path,
            {
                "schema_version": 1,
                "evaluation_id": args.evaluation_id,
                "source_digest": digest,
                "state": state,
                "phase": phase,
                **detail,
            },
        )

    def execute_phase(
        command: list[str],
        *,
        environment: dict[str, str],
        phase: str,
        predictions: Path,
        stop_record: Path,
    ) -> None:
        update_status("running", phase, checkpoint=count_lines(predictions))
        try:
            run_phase(
                command,
                root=root,
                environment=environment,
                phase=phase,
                predictions=predictions,
                stop_record=stop_record,
            )
        except SystemExit as exc:
            update_status(
                "stopped",
                phase,
                checkpoint=count_lines(predictions),
                reason=str(exc),
            )
            raise
        update_status("phase_complete", phase, checkpoint=count_lines(predictions))

    common_environment = {
        **os.environ,
        "TEXT2SQL_PLANNING_MODE": "hybrid",
        "TEXT2SQL_CANDIDATE_TOTAL_DEADLINE_SECONDS": "300",
        "TEXT2SQL_CANDIDATE_MINIMUM_CHALLENGER_SECONDS": "45",
    }
    shadow_predictions = artifact_root / "predictions" / f"{shadow_id}.jsonl"
    shadow_report = artifact_root / "reports" / f"{shadow_id}.json"
    shadow_progress = artifact_root / "reports" / f"{shadow_id}.progress.json"
    shadow_environment = {**common_environment, "TEXT2SQL_CANDIDATE_MODE": "shadow"}
    shadow_command = guarded_command(
        root,
        evaluation_id=shadow_id,
        predictions=shadow_predictions,
        report=shadow_report,
        progress=shadow_progress,
        stop_record=shadow_stop_record,
        partitions=("dev", "regression"),
    )
    execute_phase(
        guarded_command(
            root,
            evaluation_id=shadow_id,
            predictions=shadow_predictions,
            report=shadow_report,
            progress=shadow_progress,
            stop_record=shadow_stop_record,
            partitions=("dev", "regression"),
            max_batches=1,
        ),
        environment=shadow_environment,
        phase="shadow-pilot",
        predictions=shadow_predictions,
        stop_record=shadow_stop_record,
    )
    execute_phase(
        shadow_command,
        environment=shadow_environment,
        phase="shadow",
        predictions=shadow_predictions,
        stop_record=shadow_stop_record,
    )

    report: dict[str, Any] = json.loads(shadow_report.read_text(encoding="utf-8"))
    certification = certify_shadow_proofs(
        report,
        minimum_cases=5,
        minimum_accuracy=1.0,
        minimum_improvements=1,
    )
    certification_path = artifact_root / "reports" / f"{args.evaluation_id}.certification.json"
    write_certification(certification, certification_path)
    certified = [str(value) for value in certification["certified_proof_kinds"]]
    if not certified:
        update_status(
            "stopped",
            "certification",
            reason="PROOF_FAMILY_NOT_CERTIFIED",
            certification=str(certification_path),
        )
        raise SystemExit(
            "CERTIFICATION_STOP: typed proof family did not reach support>=5 across >=3 "
            "proof kinds, accuracy=100%, at least one improvement, and zero regressions"
        )

    enforce_environment = {
        **common_environment,
        "TEXT2SQL_CANDIDATE_MODE": "enforce",
        "TEXT2SQL_CERTIFIED_PROOF_KINDS": ",".join(certified),
    }
    enforce_predictions = artifact_root / "predictions" / f"{enforce_id}.jsonl"
    enforce_report = artifact_root / "reports" / f"{enforce_id}.json"
    enforce_progress = artifact_root / "reports" / f"{enforce_id}.progress.json"
    enforce_command = guarded_command(
        root,
        evaluation_id=enforce_id,
        predictions=enforce_predictions,
        report=enforce_report,
        progress=enforce_progress,
        stop_record=enforce_stop_record,
        minimum_correct=58,
    )
    update_status(
        "phase_complete",
        "certification",
        certification=str(certification_path),
        certified_proof_kinds=certified,
    )
    execute_phase(
        guarded_command(
            root,
            evaluation_id=enforce_id,
            predictions=enforce_predictions,
            report=enforce_report,
            progress=enforce_progress,
            stop_record=enforce_stop_record,
            minimum_correct=58,
            max_batches=1,
        ),
        environment=enforce_environment,
        phase="enforce-pilot",
        predictions=enforce_predictions,
        stop_record=enforce_stop_record,
    )
    execute_phase(
        enforce_command,
        environment=enforce_environment,
        phase="enforce",
        predictions=enforce_predictions,
        stop_record=enforce_stop_record,
    )
    enforce_summary = json.loads(enforce_report.read_text(encoding="utf-8"))
    update_status(
        "complete",
        "enforce",
        report=str(enforce_report),
        result_correct_count=enforce_summary.get("result_correct_count"),
        case_count=enforce_summary.get("case_count"),
    )
    print(
        "R2_PIPELINE_COMPLETE: "
        f"{enforce_summary.get('result_correct_count')}/{enforce_summary.get('case_count')}; "
        f"report={enforce_report}"
    )


if __name__ == "__main__":
    main()
