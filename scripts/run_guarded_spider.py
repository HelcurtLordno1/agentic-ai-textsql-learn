"""Run a pinned Spider manifest with one-case checkpoints and continuous laptop guards."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from agentic_text2sql.hardware import (
    PROFILES,
    ProfileName,
    ResourceLimits,
    ResourceSample,
    sample_resources,
    unsafe_reason,
)
from agentic_text2sql_eval.spider_release import SpiderReleaseManifest


def count_predictions(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(bool(line.strip()) for line in path.read_text(encoding="utf-8").splitlines())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def unload_models(base_url: str) -> None:
    with httpx.Client(base_url=base_url, timeout=30) as client:
        for model in ("qwen3:14b-q4_K_M", "bge-m3:latest"):
            try:
                client.post(
                    "/api/generate", json={"model": model, "prompt": "", "keep_alive": 0}
                ).raise_for_status()
            except httpx.HTTPError:
                pass


def stop_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)


def maximum_observation(peak: ResourceSample, current: ResourceSample) -> ResourceSample:
    return ResourceSample(
        available_ram_gib=min(peak.available_ram_gib, current.available_ram_gib),
        swap_used_gib=max(peak.swap_used_gib, current.swap_used_gib),
        gpu_memory_mib=max(peak.gpu_memory_mib, current.gpu_memory_mib),
        gpu_temperature_c=max(peak.gpu_temperature_c, current.gpu_temperature_c),
        gpu_power_w=max(peak.gpu_power_w, current.gpu_power_w),
        gpu_utilization_pct=max(peak.gpu_utilization_pct, current.gpu_utilization_pct),
        gpu_graphics_clock_mhz=max(peak.gpu_graphics_clock_mhz, current.gpu_graphics_clock_mhz),
    )


class GuardStop(Exception):
    def __init__(self, kind: str, reason: str, peak: ResourceSample) -> None:
        super().__init__(reason)
        self.kind = kind
        self.reason = reason
        self.peak = peak


def run_monitored_child(
    command: list[str],
    *,
    root: Path,
    environment: dict[str, str],
    limits: ResourceLimits,
    initial_peak: ResourceSample,
    sample_seconds: float,
    timeout_seconds: float,
) -> tuple[int, ResourceSample]:
    """Stop the whole child group on a monitor failure, resource breach, or deadline."""
    process = subprocess.Popen(command, cwd=root, env=environment, start_new_session=True)
    peak = initial_peak
    started = time.monotonic()
    try:
        while process.poll() is None:
            try:
                current = sample_resources()
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                raise GuardStop(
                    "monitor_failure", f"monitor failure: {type(exc).__name__}", peak
                ) from exc
            peak = maximum_observation(peak, current)
            if reason := unsafe_reason(current, limits):
                raise GuardStop("resource_threshold", reason, peak)
            if time.monotonic() - started >= timeout_seconds:
                raise GuardStop("batch_deadline", f"child deadline {timeout_seconds:.0f}s", peak)
            time.sleep(sample_seconds)
    except (GuardStop, KeyboardInterrupt):
        stop_process_group(process)
        raise
    return process.returncode, peak


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=(ProfileName.SPIDER_PAPER2.value,), required=True)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--cooldown-seconds", type=int, default=60)
    parser.add_argument("--sample-seconds", type=float, default=0.5)
    parser.add_argument("--batch-timeout-seconds", type=float, default=360)
    parser.add_argument("--evaluation-timeout-seconds", type=float, default=1800)
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--phase", choices=("pilot", "inference"), default="inference")
    parser.add_argument("--evaluation-id", required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--progress-report", type=Path, required=True)
    parser.add_argument("--stop-record", type=Path, required=True)
    args = parser.parse_args()
    profile = PROFILES[ProfileName(args.profile)]
    if args.stop_record.is_file():
        raise SystemExit(f"RESOURCE_STOP_LOCKED: {args.stop_record}")
    if args.batch_size != 1 or args.batch_size > profile.batch_size:
        raise SystemExit("Spider laptop batch size must be 1")
    if not profile.cooldown_seconds <= args.cooldown_seconds <= 300:
        raise SystemExit("cooldown must be at least the profile minimum of 60 seconds")
    if args.sample_seconds != 0.5:
        raise SystemExit("Spider laptop resource sampling must be 0.5 seconds")
    if not 60 <= args.batch_timeout_seconds <= 900:
        raise SystemExit("batch timeout must be between 60 and 900 seconds")
    if not 60 <= args.evaluation_timeout_seconds <= 3600:
        raise SystemExit("evaluation timeout must be between 60 and 3600 seconds")
    if args.max_batches is not None and args.max_batches < 1:
        raise SystemExit("max-batches must be positive")
    manifest = SpiderReleaseManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
    if manifest.benchmark_profile != "laptop-stratified" or manifest.case_count != 200:
        raise SystemExit("Spider R2 comparison requires the pinned laptop-stratified 200 manifest")

    try:
        peak = sample_resources()
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise SystemExit(
            f"RESOURCE_GUARD_REFUSED_START: monitor failure {type(exc).__name__}"
        ) from None
    if reason := unsafe_reason(peak, profile.limits):
        raise SystemExit(f"RESOURCE_GUARD_REFUSED_START: {reason}")

    root = Path(__file__).resolve().parents[1]
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    environment = {
        **os.environ,
        **profile.ollama_environment(),
        "OLLAMA_BASE_URL": base_url,
        "TEXT2SQL_PLANNING_MODE": "hybrid",
        "TEXT2SQL_CANDIDATE_MODE": "legacy",
        "TEXT2SQL_RESOURCE_PROFILE": profile.name.value,
    }
    total_cases = manifest.case_count
    checkpoint = count_predictions(args.predictions)
    if checkpoint > total_cases:
        raise SystemExit("Spider checkpoint exceeds manifest case count")
    batches = 0

    def status(state: str, phase: str, **detail: object) -> None:
        write_json(
            args.progress_report,
            {
                "evaluation_id": args.evaluation_id,
                "state": state,
                "phase": phase,
                "checkpoint": count_predictions(args.predictions),
                "total_cases": total_cases,
                "observed_peak": peak.__dict__,
                **detail,
            },
        )

    def command(*, evaluate_only: bool) -> list[str]:
        output = [
            "uv",
            "run",
            "python",
            "scripts/run_benchmark.py",
            "--manifest",
            str(args.manifest),
            "--predictions",
            str(args.predictions),
            "--report",
            str(args.report),
            "--evaluation-id",
            args.evaluation_id,
            "--correction",
            "--resume",
        ]
        if evaluate_only:
            output.append("--evaluate-only")
        else:
            output.extend(("--inference-only", "--max-new-cases", "1"))
        return output

    try:
        while checkpoint < total_cases:
            if args.stop_record.is_file():
                status("stopped", args.phase, reason="guarded_server_stop_record")
                raise SystemExit("RESOURCE_STOP_LOCKED: guarded server stopped")
            try:
                current = sample_resources()
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                raise GuardStop(
                    "monitor_failure", f"monitor failure: {type(exc).__name__}", peak
                ) from exc
            peak = maximum_observation(peak, current)
            if reason := unsafe_reason(current, profile.limits):
                raise GuardStop("resource_threshold", reason, peak)
            status("running", args.phase)
            before = checkpoint
            returncode, peak = run_monitored_child(
                command(evaluate_only=False),
                root=root,
                environment=environment,
                limits=profile.limits,
                initial_peak=peak,
                sample_seconds=args.sample_seconds,
                timeout_seconds=args.batch_timeout_seconds,
            )
            checkpoint = count_predictions(args.predictions)
            unload_models(base_url)
            if returncode != 0:
                status("stopped", args.phase, reason=f"child_exit={returncode}")
                raise SystemExit(returncode)
            if checkpoint != before + 1:
                status("stopped", args.phase, reason="CHECKPOINT_PROGRESS_INVALID")
                raise SystemExit("CHECKPOINT_PROGRESS_INVALID")
            batches += 1
            status("running", "cooldown")
            print(
                f"guarded Spider case complete: {checkpoint}/{total_cases}; "
                f"cooling {args.cooldown_seconds}s; observed_peak={json.dumps(peak.__dict__)}",
                flush=True,
            )
            if checkpoint < total_cases:
                time.sleep(args.cooldown_seconds)
            if args.max_batches is not None and batches >= args.max_batches:
                status("pilot_complete", args.phase)
                print(
                    json.dumps(
                        {
                            "status": "pilot_complete",
                            "checkpoint": checkpoint,
                            "peak": peak.__dict__,
                        }
                    ),
                    flush=True,
                )
                return

        if args.report.is_file():
            existing = json.loads(args.report.read_text(encoding="utf-8"))
            if (
                existing.get("evaluation_id") != args.evaluation_id
                or existing.get("case_count") != total_cases
            ):
                raise SystemExit("SPIDER_REPORT_MISMATCH: existing final report")
            status(
                "complete", "evaluation", result_correct_count=existing.get("result_correct_count")
            )
            print(json.dumps({"status": "already_complete", "checkpoint": checkpoint}), flush=True)
            return
        if args.stop_record.is_file():
            status("stopped", "evaluation", reason="guarded_server_stop_record")
            raise SystemExit("RESOURCE_STOP_LOCKED: guarded server stopped")
        status("running", "evaluation")
        returncode, peak = run_monitored_child(
            command(evaluate_only=True),
            root=root,
            environment=environment,
            limits=profile.limits,
            initial_peak=peak,
            sample_seconds=args.sample_seconds,
            timeout_seconds=args.evaluation_timeout_seconds,
        )
        if returncode != 0:
            status("stopped", "evaluation", reason=f"evaluator_exit={returncode}")
            raise SystemExit(returncode)
        report = json.loads(args.report.read_text(encoding="utf-8"))
        if (
            report.get("evaluation_id") != args.evaluation_id
            or report.get("case_count") != total_cases
        ):
            raise SystemExit("SPIDER_REPORT_MISMATCH: completed evaluation")
        status("complete", "evaluation", result_correct_count=report.get("result_correct_count"))
        print(
            f"R2_SPIDER_COMPLETE: {report['result_correct_count']}/{total_cases}; "
            f"report={args.report}",
            flush=True,
        )
    except GuardStop as exc:
        unload_models(base_url)
        peak = maximum_observation(peak, exc.peak)
        write_json(
            args.stop_record,
            {
                "stop_kind": exc.kind,
                "reason": exc.reason,
                "checkpoint": count_predictions(args.predictions),
                "total_cases": total_cases,
                "observed_peak": peak.__dict__,
            },
        )
        status("stopped", args.phase, reason=exc.reason, stop_kind=exc.kind)
        print(
            f"RESOURCE_GUARD_STOP: {exc.reason}; "
            f"checkpoint={count_predictions(args.predictions)}/{total_cases}",
            flush=True,
        )
        raise SystemExit(75) from exc
    except KeyboardInterrupt:
        unload_models(base_url)
        status("paused", args.phase, reason="operator_interrupt")
        print(
            f"SPIDER_PAUSED: checkpoint={count_predictions(args.predictions)}/{total_cases}",
            flush=True,
        )
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
