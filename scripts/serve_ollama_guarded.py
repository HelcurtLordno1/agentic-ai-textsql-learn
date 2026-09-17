"""Start Ollama under a bounded CPU profile and stop it on a resource breach."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

from agentic_text2sql.hardware import (
    PROFILES,
    ProfileName,
    ResourceSample,
    sample_resources,
    unsafe_reason,
)


def stop_process_group(process: subprocess.Popen[bytes]) -> None:
    """Stop Ollama and its runners without leaving model memory resident."""
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
        "--profile",
        choices=tuple(ProfileName),
        default=ProfileName.INTERACTIVE,
    )
    parser.add_argument("--models-dir", type=Path)
    parser.add_argument("--host", default="127.0.0.1:11434")
    parser.add_argument("--sample-seconds", type=float, default=0.5)
    parser.add_argument("--stop-record", type=Path)
    args = parser.parse_args()
    if not 0.5 <= args.sample_seconds <= 10:
        raise SystemExit("sample-seconds must be between 0.5 and 10")

    profile = PROFILES[ProfileName(args.profile)]
    if args.stop_record is not None and args.stop_record.is_file():
        raise SystemExit(f"RESOURCE_STOP_LOCKED: {args.stop_record}")
    try:
        preflight = sample_resources()
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise SystemExit(
            f"RESOURCE_GUARD_REFUSED_START: monitor failure {type(exc).__name__}"
        ) from None
    reason = unsafe_reason(preflight, profile.limits)
    if reason:
        raise SystemExit(f"RESOURCE_GUARD_REFUSED_START: {reason}")

    environment = {
        **os.environ,
        **profile.ollama_environment(),
        "OLLAMA_HOST": args.host,
    }
    if args.models_dir is not None:
        environment["OLLAMA_MODELS"] = str(args.models_dir.resolve())
    command = [
        "taskset",
        "-c",
        f"0-{profile.cpu_cores - 1}",
        "nice",
        "-n",
        "10",
        "ollama",
        "serve",
    ]
    print(
        json.dumps(
            {
                "status": "starting",
                "profile": profile.model_dump(mode="json"),
                "command": command,
                "preflight": preflight.__dict__,
            },
            indent=2,
        ),
        flush=True,
    )
    process = subprocess.Popen(command, env=environment, start_new_session=True)
    peak = preflight
    try:
        while process.poll() is None:
            time.sleep(args.sample_seconds)
            try:
                current = sample_resources()
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                stop_process_group(process)
                if args.stop_record is not None:
                    write_stop_record(
                        args.stop_record,
                        "monitor_failure",
                        f"monitor failure: {type(exc).__name__}",
                        peak,
                    )
                raise SystemExit(
                    f"RESOURCE_GUARD_STOP: monitor failure {type(exc).__name__}"
                ) from exc
            peak = type(current)(
                available_ram_gib=min(peak.available_ram_gib, current.available_ram_gib),
                swap_used_gib=max(peak.swap_used_gib, current.swap_used_gib),
                gpu_memory_mib=max(peak.gpu_memory_mib, current.gpu_memory_mib),
                gpu_temperature_c=max(peak.gpu_temperature_c, current.gpu_temperature_c),
                gpu_power_w=max(peak.gpu_power_w, current.gpu_power_w),
                gpu_utilization_pct=max(peak.gpu_utilization_pct, current.gpu_utilization_pct),
                gpu_graphics_clock_mhz=max(
                    peak.gpu_graphics_clock_mhz, current.gpu_graphics_clock_mhz
                ),
            )
            reason = unsafe_reason(current, profile.limits)
            if reason:
                stop_process_group(process)
                if args.stop_record is not None:
                    write_stop_record(args.stop_record, "resource_threshold", reason, peak)
                print(
                    json.dumps(
                        {
                            "status": "resource_guard_stop",
                            "reason": reason,
                            "peak": peak.__dict__,
                        },
                        indent=2,
                    )
                )
                raise SystemExit(75)
    except KeyboardInterrupt:
        stop_process_group(process)
        print(json.dumps({"status": "stopped", "peak": peak.__dict__}, indent=2))
        return
    raise SystemExit(process.returncode)


def write_stop_record(
    path: Path,
    stop_kind: str,
    reason: str,
    peak: ResourceSample,
) -> None:
    """Persist a fail-closed lock before an operator can resume a stopped suite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stop_kind": stop_kind,
        "reason": reason,
        "observed_peak": peak.__dict__,
    }
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    main()
