"""Run Olist-60 in cooled batches with hard laptop resource guards."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

GIB = 1024**3


@dataclass(frozen=True)
class Sample:
    available_ram_gib: float
    swap_used_gib: float
    gpu_memory_mib: int
    gpu_temperature_c: int
    gpu_power_w: float
    gpu_utilization_pct: int


def _memory() -> tuple[float, float]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, value = line.split(":", maxsplit=1)
        values[key] = int(value.split()[0]) * 1024
    return values["MemAvailable"] / GIB, (values["SwapTotal"] - values["SwapFree"]) / GIB


def sample() -> Sample:
    available, swap_used = _memory()
    output = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=memory.used,temperature.gpu,power.draw,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        timeout=5,
    ).strip()
    memory, temperature, power, utilization = [item.strip() for item in output.split(",")]
    return Sample(
        available_ram_gib=available,
        swap_used_gib=swap_used,
        gpu_memory_mib=int(memory),
        gpu_temperature_c=int(temperature),
        gpu_power_w=float(power),
        gpu_utilization_pct=int(utilization),
    )


def unsafe_reason(
    current: Sample,
    *,
    minimum_available_ram_gib: float,
    maximum_swap_used_gib: float,
    maximum_gpu_memory_mib: int,
    maximum_gpu_temperature_c: int,
    maximum_gpu_power_w: float,
) -> str | None:
    checks = (
        (
            current.available_ram_gib < minimum_available_ram_gib,
            f"available RAM {current.available_ram_gib:.1f} GiB",
        ),
        (current.swap_used_gib >= maximum_swap_used_gib, f"swap {current.swap_used_gib:.1f} GiB"),
        (
            current.gpu_memory_mib >= maximum_gpu_memory_mib,
            f"VRAM {current.gpu_memory_mib} MiB",
        ),
        (
            current.gpu_temperature_c >= maximum_gpu_temperature_c,
            f"GPU temperature {current.gpu_temperature_c} C",
        ),
        (current.gpu_power_w >= maximum_gpu_power_w, f"GPU power {current.gpu_power_w:.1f} W"),
    )
    return next((message for failed, message in checks if failed), None)


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--cooldown-seconds", type=int, default=45)
    parser.add_argument("--minimum-available-ram-gib", type=float, default=10)
    parser.add_argument("--maximum-swap-used-gib", type=float, default=1)
    parser.add_argument("--maximum-gpu-memory-mib", type=int, default=11776)
    parser.add_argument("--maximum-gpu-temperature-c", type=int, default=76)
    parser.add_argument("--maximum-gpu-power-w", type=float, default=95)
    parser.add_argument("--ollama-num-gpu", type=int, default=20)
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args()
    if args.batch_size not in {1, 2, 3}:
        raise SystemExit("batch-size must be between 1 and 3")

    root = Path(__file__).resolve().parents[1]
    predictions = root / "evals/predictions/olist-p5-60.jsonl"
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    environment = {
        **os.environ,
        "OLLAMA_BASE_URL": base_url,
        "TEXT2SQL_OLLAMA_NUM_GPU": str(args.ollama_num_gpu),
        "TEXT2SQL_REQUEST_TIMEOUT_SECONDS": "240",
    }
    retry_counts: dict[int, int] = {}
    peak: dict[str, float] = {
        "ram_used_gib": 0,
        "swap_used_gib": 0,
        "gpu_memory_mib": 0,
        "gpu_temperature_c": 0,
        "gpu_power_w": 0,
    }

    batches = 0
    while count_predictions(predictions) < 60:
        before = count_predictions(predictions)
        command = [
            "uv",
            "run",
            "python",
            "scripts/run_olist_acceptance.py",
            "--correction",
            "--resume",
            "--max-new-cases",
            str(args.batch_size),
        ]
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
        process = subprocess.Popen(command, cwd=root, env=environment)
        reason: str | None = None
        while process.poll() is None:
            try:
                current = sample()
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                reason = f"monitor failure: {type(exc).__name__}"
                break
            total_ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / GIB
            peak["ram_used_gib"] = max(peak["ram_used_gib"], total_ram - current.available_ram_gib)
            peak["swap_used_gib"] = max(peak["swap_used_gib"], current.swap_used_gib)
            peak["gpu_memory_mib"] = max(peak["gpu_memory_mib"], current.gpu_memory_mib)
            peak["gpu_temperature_c"] = max(peak["gpu_temperature_c"], current.gpu_temperature_c)
            peak["gpu_power_w"] = max(peak["gpu_power_w"], current.gpu_power_w)
            reason = unsafe_reason(
                current,
                minimum_available_ram_gib=args.minimum_available_ram_gib,
                maximum_swap_used_gib=args.maximum_swap_used_gib,
                maximum_gpu_memory_mib=args.maximum_gpu_memory_mib,
                maximum_gpu_temperature_c=args.maximum_gpu_temperature_c,
                maximum_gpu_power_w=args.maximum_gpu_power_w,
            )
            if reason:
                break
            time.sleep(2)
        if reason:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
            unload_models(base_url)
            print(f"RESOURCE_GUARD_STOP: {reason}; checkpoint={count_predictions(predictions)}/60")
            print(json.dumps({"observed_peak": peak}, indent=2))
            raise SystemExit(75)
        if process.returncode != 0:
            unload_models(base_url)
            raise SystemExit(process.returncode)
        after = count_predictions(predictions)
        if retrying and after == before:
            retry_counts[before] = retry_counts.get(before, 0) + 1
        elif after <= before and after < 60:
            raise SystemExit("acceptance batch made no checkpoint progress")
        unload_models(base_url)
        batches += 1
        print(
            f"guarded batch complete: {after}/60; cooling {args.cooldown_seconds}s; "
            f"observed_peak={json.dumps(peak, sort_keys=True)}"
        )
        if args.max_batches is not None and batches >= args.max_batches:
            print(json.dumps({"status": "pilot_complete", "checkpoint": after, "peak": peak}))
            return
        if after < 60:
            time.sleep(args.cooldown_seconds)

    print(json.dumps({"status": "complete", "cases": 60, "observed_peak": peak}, indent=2))


if __name__ == "__main__":
    main()
