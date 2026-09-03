"""Run Olist-60 in cooled batches with hard laptop resource guards."""

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
    GIB,
    PROFILES,
    ProfileName,
    sample_resources,
    unsafe_reason,
)


def unload_models(base_url: str) -> None:
    with httpx.Client(base_url=base_url, timeout=15) as client:
        for model in ("qwen3:14b-q4_K_M", "bge-m3:latest"):
            try:
                client.post(
                    "/api/generate", json={"model": model, "prompt": "", "keep_alive": 0}
                ).raise_for_status()
            except httpx.HTTPError:
                pass


def count_predictions(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(bool(line.strip()) for line in path.read_text(encoding="utf-8").splitlines())


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
        "--profile", choices=[item.value for item in ProfileName], default=ProfileName.ACCEPTANCE
    )
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--cooldown-seconds", type=int)
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--sample-seconds", type=float, default=0.5)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--only-case-id", action="append", default=[])
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--evaluation-id", default="olist-acceptance-60-p5-v1")
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
    if not 0.5 <= args.sample_seconds <= 5:
        raise SystemExit("sample-seconds must be between 0.5 and 5")
    limits = profile.limits

    root = Path(__file__).resolve().parents[1]
    cases = args.cases or root / "evals/configs/olist-acceptance-60.jsonl"
    case_ids = [
        json.loads(line)["id"]
        for line in cases.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.only_case_id:
        unknown = set(args.only_case_id) - set(case_ids)
        if unknown:
            raise SystemExit(f"unknown case IDs: {', '.join(sorted(unknown))}")
        total_cases = len(set(args.only_case_id))
    else:
        total_cases = len(case_ids)
    predictions = args.predictions or root / "evals/predictions/olist-p5-60.jsonl"
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    environment = {
        **os.environ,
        "OLLAMA_BASE_URL": base_url,
        "TEXT2SQL_REQUEST_TIMEOUT_SECONDS": "240",
        **profile.ollama_environment(),
    }
    try:
        preflight = sample_resources()
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise SystemExit(
            f"RESOURCE_GUARD_REFUSED_START: monitor failure {type(exc).__name__}"
        ) from exc
    preflight_reason = unsafe_reason(preflight, limits)
    if preflight_reason:
        raise SystemExit(f"RESOURCE_GUARD_REFUSED_START: {preflight_reason}")

    total_ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / GIB
    retry_counts: dict[int, int] = {}
    peak: dict[str, float] = {
        "ram_used_gib": total_ram - preflight.available_ram_gib,
        "swap_used_gib": preflight.swap_used_gib,
        "gpu_memory_mib": preflight.gpu_memory_mib,
        "gpu_temperature_c": preflight.gpu_temperature_c,
        "gpu_power_w": preflight.gpu_power_w,
    }

    batches = 0
    while count_predictions(predictions) < total_cases:
        before = count_predictions(predictions)
        command = [
            "uv",
            "run",
            "python",
            "scripts/run_olist_acceptance.py",
            "--correction",
            "--resume",
            "--max-new-cases",
            str(batch_size),
            "--predictions",
            str(predictions),
            "--report",
            str(args.report or root / "evals/reports/olist-p5-60.json"),
            "--evaluation-id",
            args.evaluation_id,
            "--cases",
            str(cases),
        ]
        for case_id in args.only_case_id:
            command.extend(("--only-case-id", case_id))
        retrying = False
        if predictions.is_file() and retry_counts.get(before, 0) < 1:
            last_payload = json.loads(
                next(
                    line
                    for line in reversed(predictions.read_text(encoding="utf-8").splitlines())
                    if line
                )
            )
            last_result = last_payload["result"]
            retrying = last_result["status"] == "MODEL_ERROR" and any(
                marker in (last_result.get("safe_message") or "")
                for marker in ("ReadTimeout", "ProviderUnavailable", "request failed")
            )
            if retrying:
                command.append("--retry-last-infrastructure-error")
        process = subprocess.Popen(command, cwd=root, env=environment, start_new_session=True)
        reason: str | None = None
        try:
            while process.poll() is None:
                current = sample_resources()
                peak["ram_used_gib"] = max(
                    peak["ram_used_gib"], total_ram - current.available_ram_gib
                )
                peak["swap_used_gib"] = max(peak["swap_used_gib"], current.swap_used_gib)
                peak["gpu_memory_mib"] = max(peak["gpu_memory_mib"], current.gpu_memory_mib)
                peak["gpu_temperature_c"] = max(
                    peak["gpu_temperature_c"], current.gpu_temperature_c
                )
                peak["gpu_power_w"] = max(peak["gpu_power_w"], current.gpu_power_w)
                reason = unsafe_reason(current, limits)
                if reason:
                    break
                time.sleep(args.sample_seconds)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            reason = f"monitor failure: {type(exc).__name__}"
        except KeyboardInterrupt:
            stop_process_group(process)
            unload_models(base_url)
            print(f"GUARDED_RUN_INTERRUPTED: checkpoint={count_predictions(predictions)}")
            return
        if reason:
            stop_process_group(process)
            unload_models(base_url)
            print(
                f"RESOURCE_GUARD_STOP: {reason}; "
                f"checkpoint={count_predictions(predictions)}/{total_cases}"
            )
            print(json.dumps({"observed_peak": peak}, indent=2))
            raise SystemExit(75)
        if process.returncode != 0:
            unload_models(base_url)
            raise SystemExit(process.returncode)
        after = count_predictions(predictions)
        if retrying and after == before:
            retry_counts[before] = retry_counts.get(before, 0) + 1
        elif after <= before and after < total_cases:
            raise SystemExit("acceptance batch made no checkpoint progress")
        unload_models(base_url)
        batches += 1
        print(
            f"guarded batch complete: {after}/{total_cases}; cooling {cooldown_seconds}s; "
            f"observed_peak={json.dumps(peak, sort_keys=True)}"
        )
        if args.max_batches is not None and batches >= args.max_batches:
            print(json.dumps({"status": "pilot_complete", "checkpoint": after, "peak": peak}))
            return
        if after < total_cases:
            time.sleep(cooldown_seconds)

    print(json.dumps({"status": "complete", "cases": total_cases, "observed_peak": peak}, indent=2))


if __name__ == "__main__":
    main()
