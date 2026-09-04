"""Run a Spider release manifest in cooled, resumable batches under the laptop guard."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import httpx

from agentic_text2sql.hardware import PROFILES, ProfileName, sample_resources, unsafe_reason


def count_predictions(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(bool(line.strip()) for line in path.read_text(encoding="utf-8").splitlines())


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile", choices=[item.value for item in ProfileName], default=ProfileName.BENCHMARK
    )
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--cooldown-seconds", type=int)
    parser.add_argument("--sample-seconds", type=float, default=0.5)
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    profile = PROFILES[ProfileName(args.profile)]
    batch_size = args.batch_size if args.batch_size is not None else profile.batch_size
    cooldown_seconds = (
        args.cooldown_seconds if args.cooldown_seconds is not None else profile.cooldown_seconds
    )
    if not 1 <= batch_size <= profile.batch_size:
        raise SystemExit(f"batch-size must be between 1 and profile maximum {profile.batch_size}")
    if not profile.cooldown_seconds <= cooldown_seconds <= 300:
        raise SystemExit(
            f"cooldown-seconds must be between profile minimum {profile.cooldown_seconds} and 300"
        )
    if not 0.5 <= args.sample_seconds <= 10:
        raise SystemExit("sample-seconds must be between 0.5 and 10")

    root = Path(__file__).resolve().parents[1]
    manifest_payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    total_cases = int(manifest_payload["case_count"])
    if total_cases < 1:
        raise SystemExit("manifest case_count must be positive")
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    environment = {
        **os.environ,
        "OLLAMA_BASE_URL": base_url,
        "TEXT2SQL_REQUEST_TIMEOUT_SECONDS": "240",
        **profile.ollama_environment(),
    }
    batches = 0
    observed_peak = sample_resources()
    preflight_reason = unsafe_reason(observed_peak, profile.limits)
    if preflight_reason:
        raise SystemExit(f"RESOURCE_GUARD_REFUSED_START: {preflight_reason}")
    while count_predictions(args.predictions) < total_cases:
        before = count_predictions(args.predictions)
        command = [
            "uv",
            "run",
            "python",
            "scripts/run_benchmark.py",
            "--correction",
            "--resume",
            "--max-new-cases",
            str(batch_size),
            "--predictions",
            str(args.predictions),
            "--report",
            str(args.report),
            "--manifest",
            str(args.manifest),
        ]
        process = subprocess.Popen(command, cwd=root, env=environment, start_new_session=True)
        reason: str | None = None
        while process.poll() is None:
            try:
                current = sample_resources()
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                reason = f"monitor failure: {type(exc).__name__}"
                stop_process_group(process)
                break
            observed_peak = type(current)(
                available_ram_gib=min(observed_peak.available_ram_gib, current.available_ram_gib),
                swap_used_gib=max(observed_peak.swap_used_gib, current.swap_used_gib),
                gpu_memory_mib=max(observed_peak.gpu_memory_mib, current.gpu_memory_mib),
                gpu_temperature_c=max(observed_peak.gpu_temperature_c, current.gpu_temperature_c),
                gpu_power_w=max(observed_peak.gpu_power_w, current.gpu_power_w),
                gpu_utilization_pct=max(
                    observed_peak.gpu_utilization_pct, current.gpu_utilization_pct
                ),
                gpu_graphics_clock_mhz=max(
                    observed_peak.gpu_graphics_clock_mhz,
                    current.gpu_graphics_clock_mhz,
                ),
            )
            reason = unsafe_reason(current, profile.limits)
            if reason:
                stop_process_group(process)
                break
            time.sleep(args.sample_seconds)
        after = count_predictions(args.predictions)
        if reason:
            unload_models(base_url)
            print(f"RESOURCE_GUARD_STOP: {reason}; checkpoint={after}/{total_cases}")
            print(json.dumps({"observed_peak": observed_peak.__dict__}, indent=2))
            raise SystemExit(75)
        if process.returncode != 0:
            unload_models(base_url)
            raise SystemExit(process.returncode)
        if after <= before:
            raise SystemExit("Spider batch made no checkpoint progress")
        unload_models(base_url)
        batches += 1
        print(
            json.dumps(
                {
                    "status": "batch_complete",
                    "checkpoint": after,
                    "total": total_cases,
                    "observed_peak": observed_peak.__dict__,
                }
            ),
            flush=True,
        )
        if args.max_batches is not None and batches >= args.max_batches:
            return
        if after < total_cases:
            time.sleep(cooldown_seconds)


if __name__ == "__main__":
    main()
