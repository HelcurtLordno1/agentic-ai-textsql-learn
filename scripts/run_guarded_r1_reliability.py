"""Resume the R1 reliability benchmark one cooled case at a time under hard guards."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import httpx

from agentic_text2sql.hardware import (
    PROFILES,
    ProfileName,
    ResourceSample,
    sample_resources,
    unsafe_reason,
)

TOTAL_CASES = 100


def count_predictions(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(bool(line.strip()) for line in path.read_text(encoding="utf-8").splitlines())


def unload_model(base_url: str, model: str) -> None:
    try:
        with httpx.Client(base_url=base_url, timeout=15) as client:
            client.post(
                "/api/generate",
                json={"model": model, "prompt": "", "stream": False, "keep_alive": 0},
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


def update_peak(peak: ResourceSample, current: ResourceSample) -> ResourceSample:
    return ResourceSample(
        available_ram_gib=min(peak.available_ram_gib, current.available_ram_gib),
        swap_used_gib=max(peak.swap_used_gib, current.swap_used_gib),
        gpu_memory_mib=max(peak.gpu_memory_mib, current.gpu_memory_mib),
        gpu_temperature_c=max(peak.gpu_temperature_c, current.gpu_temperature_c),
        gpu_power_w=max(peak.gpu_power_w, current.gpu_power_w),
        gpu_utilization_pct=max(peak.gpu_utilization_pct, current.gpu_utilization_pct),
        gpu_graphics_clock_mhz=max(peak.gpu_graphics_clock_mhz, current.gpu_graphics_clock_mhz),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--predictions", type=Path, default=Path("evals/predictions/practiq-r1-100-v5.jsonl")
    )
    parser.add_argument("--report", type=Path, default=Path("evals/reports/practiq-r1-100-v5.json"))
    parser.add_argument("--sample-seconds", type=float, default=0.5)
    parser.add_argument("--cooldown-seconds", type=int)
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args()
    if not 0.5 <= args.sample_seconds <= 5:
        raise SystemExit("sample-seconds must be between 0.5 and 5")

    profile = PROFILES[ProfileName.R1_RELIABILITY]
    cooldown = profile.cooldown_seconds if args.cooldown_seconds is None else args.cooldown_seconds
    if not profile.cooldown_seconds <= cooldown <= 300:
        raise SystemExit(f"cooldown-seconds must be between {profile.cooldown_seconds} and 300")
    root = Path(__file__).resolve().parents[1]
    predictions = (root / args.predictions).resolve()
    report = (root / args.report).resolve()
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.environ.get("TEXT2SQL_OLLAMA_MODEL", "qwen3:14b-q4_K_M")
    environment = {
        **os.environ,
        **profile.ollama_environment(),
        "OLLAMA_BASE_URL": base_url,
        "TEXT2SQL_OLLAMA_MODEL": model,
    }
    peak = sample_resources()
    reason = unsafe_reason(peak, profile.limits)
    if reason:
        raise SystemExit(f"RESOURCE_GUARD_REFUSED_START: {reason}")

    batches = 0
    while count_predictions(predictions) < TOTAL_CASES:
        before = count_predictions(predictions)
        command = [
            str(root / ".venv/bin/python"),
            "scripts/run_r1_reliability_benchmark.py",
            "--predictions",
            str(predictions),
            "--report",
            str(report),
            "--max-new-cases",
            "1",
        ]
        process = subprocess.Popen(command, cwd=root, env=environment, start_new_session=True)
        reason = None
        while process.poll() is None:
            try:
                current = sample_resources()
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                reason = f"monitor failure: {type(exc).__name__}"
                break
            peak = update_peak(peak, current)
            reason = unsafe_reason(current, profile.limits)
            if reason:
                break
            time.sleep(args.sample_seconds)
        if reason:
            stop_process_group(process)
            unload_model(base_url, model)
            print(
                json.dumps(
                    {
                        "status": "resource_guard_stop",
                        "reason": reason,
                        "checkpoint": count_predictions(predictions),
                        "peak": peak.__dict__,
                    },
                    indent=2,
                )
            )
            raise SystemExit(75)
        if process.returncode != 0:
            unload_model(base_url, model)
            raise SystemExit(process.returncode)
        after = count_predictions(predictions)
        if after <= before:
            unload_model(base_url, model)
            raise SystemExit("guarded batch made no checkpoint progress")
        unload_model(base_url, model)
        batches += 1
        print(
            json.dumps({"status": "batch_complete", "checkpoint": after, "peak": peak.__dict__}),
            flush=True,
        )
        if args.max_batches is not None and batches >= args.max_batches:
            return
        if after < TOTAL_CASES:
            time.sleep(cooldown)


if __name__ == "__main__":
    main()
