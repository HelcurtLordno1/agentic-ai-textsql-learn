"""Run a Spider release manifest in cooled, resumable batches under the laptop guard."""

from __future__ import annotations

import argparse
import json
import os
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile", choices=[item.value for item in ProfileName], default=ProfileName.INTERACTIVE
    )
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--cooldown-seconds", type=int, default=20)
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 20:
        raise SystemExit("batch-size must be between 1 and 20")
    if not 0 <= args.cooldown_seconds <= 300:
        raise SystemExit("cooldown-seconds must be between 0 and 300")

    root = Path(__file__).resolve().parents[1]
    manifest_payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    total_cases = int(manifest_payload["case_count"])
    if total_cases < 1:
        raise SystemExit("manifest case_count must be positive")
    profile = PROFILES[ProfileName(args.profile)]
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    environment = {
        **os.environ,
        "OLLAMA_BASE_URL": base_url,
        "TEXT2SQL_REQUEST_TIMEOUT_SECONDS": "240",
        **profile.ollama_environment(),
    }
    batches = 0
    observed_peak = sample_resources()
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
            str(args.batch_size),
            "--predictions",
            str(args.predictions),
            "--report",
            str(args.report),
            "--manifest",
            str(args.manifest),
        ]
        process = subprocess.Popen(command, cwd=root, env=environment)
        reason: str | None = None
        while process.poll() is None:
            try:
                current = sample_resources()
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                reason = f"monitor failure: {type(exc).__name__}"
                process.terminate()
                process.wait(timeout=10)
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
            )
            reason = unsafe_reason(current, profile.limits)
            if reason:
                process.terminate()
                process.wait(timeout=10)
                break
            time.sleep(1)
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
            time.sleep(args.cooldown_seconds)


if __name__ == "__main__":
    main()
