"""One-case guarded suites with durable pause/resume and truthful completion."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sys
import time
from pathlib import Path

from agentic_text2sql.hardware import PROFILES, ProfileName
from agentic_text2sql.resource_guard import ResourceGuardError, guarded_process, workload_lease
from agentic_text2sql.settings import Settings
from agentic_text2sql_eval.runtime_checkpoint import file_sha256
from agentic_text2sql_eval.suite_control import (
    SuiteState,
    boot_id,
    prediction_prefix,
    process_group_alive,
    require_complete_report,
    write_state,
)


def count_predictions(path: Path) -> int:
    return sum(bool(line.strip()) for line in path.read_text().splitlines()) if path.exists() else 0


def main(kind: str) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile", choices=[p.value for p in ProfileName], default="acceptance-safe"
    )
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--cooldown-seconds", type=int, default=60)
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--correction", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--recovery-pilot", action="store_true")
    if kind == "spider":
        parser.add_argument("--manifest", type=Path, required=True)
        parser.add_argument("--allow-dirty-source", action="store_true")
    else:
        parser.add_argument("--cases", type=Path)
        parser.add_argument("--evaluation-id", default="olist-local-construction-v1")
    args = parser.parse_args()
    if args.batch_size != 1 or args.cooldown_seconds < 60:
        raise SystemExit("Require batch-size=1 and cooldown-seconds>=60")
    if args.max_batches is not None and args.max_batches < 1:
        raise SystemExit("max-batches must be positive")
    root = Path(__file__).resolve().parents[1]
    profile = PROFILES[ProfileName(args.profile)]
    settings = Settings(**profile.ollama_environment())
    manifest = (
        args.manifest
        if kind == "spider"
        else (args.cases or root / "evals/configs/olist-acceptance-60.jsonl")
    )
    if kind == "spider":
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        ids = [case["id"] for case in payload["cases"]]
        if payload["case_count"] != len(ids):
            raise SystemExit("Manifest count disagrees with case IDs")
    else:
        ids = [json.loads(line)["id"] for line in manifest.read_text().splitlines() if line.strip()]
    if not ids or len(ids) != len(set(ids)):
        raise SystemExit("Suite must contain unique case IDs")
    config = {
        "kind": kind,
        "manifest_sha256": file_sha256(manifest),
        "manifest": str(manifest.resolve()),
        "predictions": str(args.predictions.resolve()),
        "report": str(args.report.resolve()),
        "correction": args.correction,
        "evaluation_id": args.evaluation_id if kind == "olist" else None,
        "allow_dirty_source": args.allow_dirty_source if kind == "spider" else None,
        "profile": profile.model_dump(mode="json"),
        "cooldown": args.cooldown_seconds,
        "settings": settings.model_dump(mode="json", exclude={"guarded_run"}),
    }
    identity = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    state_path = args.report.with_suffix(".suite-state.json")
    stop_path = args.report.with_suffix(".resource-stop.json")
    pause_path = args.report.with_suffix(".pause-request.json")
    environment = {
        **os.environ,
        **profile.ollama_environment(),
        "TEXT2SQL_RESOURCE_PROFILE": profile.model_dump_json(),
    }
    requested_pause = False

    def request_pause(signum: int, frame: object) -> None:
        nonlocal requested_pause
        del signum, frame
        requested_pause = True

    old_handlers = {
        sig: signal.signal(sig, request_pause) for sig in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        with workload_lease(args.report.with_suffix(".suite.lock")):
            completed = prediction_prefix(args.predictions, ids)
            previous = (
                SuiteState.model_validate_json(state_path.read_text())
                if state_path.exists()
                else None
            )
            if previous is not None and previous.identity != identity:
                raise SystemExit("Suite configuration changed; use new prediction/report paths")
            if stop_path.exists():
                raise SystemExit(
                    "Resource stop is latched; remediation and independent pilot required"
                )
            if (
                previous
                and previous.boot_id == boot_id()
                and process_group_alive(previous.child_pid)
            ):
                raise SystemExit("Stale worker is still alive; do not launch another model run")
            unclean = previous is not None and (
                previous.recovery_required
                or previous.boot_id != boot_id()
                or previous.phase in {"RUNNING", "COOLING"}
            )
            if unclean and completed < len(ids) and not args.recovery_pilot:
                raise SystemExit(
                    "Unclean stop/reboot: resume first with --recovery-pilot (one case)"
                )
            needs_final_cleanup = bool(
                completed == len(ids)
                and (previous is None or previous.cleanup_pending or previous.phase == "RUNNING")
            )
            if (
                previous
                and previous.phase == "PAUSED"
                and pause_path.exists()
                and pause_path.stat().st_mtime <= previous.updated_at
            ):
                pause_path.unlink()
            state = SuiteState(
                phase="READY",
                completed=completed,
                total=len(ids),
                identity=identity,
                boot_id=boot_id(),
                pid=os.getpid(),
                cooldown_until=previous.cooldown_until if previous else 0,
                recovery_required=unclean and completed < len(ids),
                cleanup_pending=needs_final_cleanup,
            )
            write_state(state_path, state)
            while time.time() < state.cooldown_until:
                time.sleep(max(0, min(1, state.cooldown_until - time.time())))
            command = [
                sys.executable,
                "scripts/run_benchmark.py"
                if kind == "spider"
                else "scripts/run_olist_acceptance.py",
                "--correction" if args.correction else "--no-correction",
                "--resume",
                "--max-new-cases",
                "1",
                "--predictions",
                str(args.predictions),
                "--report",
                str(args.report),
            ]
            if kind == "spider":
                command.extend(["--manifest", str(manifest)])
                if args.allow_dirty_source:
                    command.append("--allow-dirty-source")
            else:
                command.extend(["--cases", str(manifest), "--evaluation-id", args.evaluation_id])
            batches = 0

            def spawned(pid: int) -> None:
                state.child_pid = pid
                write_state(state_path, state)

            def cooling(deadline: float) -> None:
                state.phase = "COOLING"
                if not process_group_alive(state.child_pid):
                    state.child_pid = None
                    state.cleanup_pending = False
                state.completed = prediction_prefix(args.predictions, ids)
                state.cooldown_until = deadline
                write_state(state_path, state)

            while True:
                completed = prediction_prefix(args.predictions, ids)
                if completed == len(ids) and args.report.exists() and not needs_final_cleanup:
                    try:
                        require_complete_report(args.report, ids)
                    except (ValueError, OSError) as exc:
                        state.phase, state.reason = "FAILED", str(exc)
                        write_state(state_path, state)
                        raise SystemExit(f"Final report validation failed: {exc}") from exc
                    state.phase, state.completed, state.child_pid = "COMPLETE", completed, None
                    state.reason = "All predictions checkpointed and final report validated"
                    write_state(state_path, state)
                    print(
                        f"SUCCESS FINISH ALL: {completed}/{len(ids)}; report={args.report}",
                        flush=True,
                    )
                    return
                if (
                    requested_pause
                    or pause_path.exists()
                    or (args.max_batches is not None and batches >= args.max_batches)
                    or (args.recovery_pilot and batches >= 1)
                ):
                    state.phase, state.completed, state.child_pid = "PAUSED", completed, None
                    state.reason = "Operator pause or batch/pilot boundary; cooldown completed"
                    write_state(state_path, state)
                    print(
                        f"PAUSED: checkpoint={completed}/{len(ids)}; resume with identical config",
                        flush=True,
                    )
                    return
                state.phase, state.completed, state.child_pid = "RUNNING", completed, None
                state.cleanup_pending = True
                write_state(state_path, state)
                started = time.monotonic()
                try:
                    summary = guarded_process(
                        command,
                        cwd=root,
                        environment=environment,
                        base_url=settings.ollama_base_url,
                        stop_path=stop_path,
                        limits=profile.limits,
                        cooldown_seconds=args.cooldown_seconds,
                        on_spawn=spawned,
                        on_cooldown=cooling,
                    )
                    after = prediction_prefix(args.predictions, ids)
                    expected = completed + 1 if completed < len(ids) else completed
                    if after != expected:
                        raise ValueError(
                            "Batch did not persist exactly the expected case; no auto-retry"
                        )
                    needs_final_cleanup = False
                    state.recovery_required = False
                    state.cleanup_pending = False
                except (ResourceGuardError, ValueError, OSError) as exc:
                    state.phase = "RESOURCE_STOP" if stop_path.exists() else "FAILED"
                    state.completed = prediction_prefix(args.predictions, ids)
                    state.reason = str(exc)
                    # Retain the worker PID if termination failed; resume checks it.
                    if not process_group_alive(state.child_pid):
                        state.child_pid = None
                    write_state(state_path, state)
                    raise SystemExit(
                        f"STOP: {exc}; checkpoint={state.completed}/{len(ids)}"
                    ) from exc
                batches += 1
                print(
                    json.dumps(
                        {
                            "checkpoint": after,
                            "total": len(ids),
                            "batch_wall_seconds_with_cooldown": time.monotonic() - started,
                            **summary,
                        }
                    ),
                    flush=True,
                )
    finally:
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit("Use a suite-specific guarded entrypoint")
