"""Start Ollama under a bounded CPU profile and stop it on a resource breach."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

from agentic_text2sql.gpu_monitor import GpuMonitor
from agentic_text2sql.hardware import PROFILES, ProfileName, unsafe_reason
from agentic_text2sql.resource_guard import merge_peak, observe_resources
from agentic_text2sql.windows_monitor import WindowsHostMonitor


def stop_process_group(process: subprocess.Popen[bytes]) -> None:
    """Stop Ollama and its runners without leaving model memory resident."""
    if process.poll() is not None:
        return
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
            process.wait(timeout=2)
            return
        except ProcessLookupError:
            return
        except subprocess.TimeoutExpired:
            continue
    raise RuntimeError("Ollama process group did not terminate")


def main() -> None:
    host_monitor = (
        WindowsHostMonitor()
        if os.environ.get("TEXT2SQL_MONITOR_WINDOWS_HOST", "").lower() == "true"
        else None
    )
    try:
        if host_monitor is not None:
            host_monitor.__enter__()
        with GpuMonitor() as gpu_monitor:
            run_server(host_monitor, gpu_monitor)
    finally:
        if host_monitor is not None:
            host_monitor.close()


def run_server(host_monitor: WindowsHostMonitor | None, gpu_monitor: GpuMonitor) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        choices=tuple(ProfileName),
        default=ProfileName.INTERACTIVE,
    )
    parser.add_argument("--models-dir", type=Path)
    parser.add_argument("--host", default="127.0.0.1:11434")
    parser.add_argument("--sample-seconds", type=float, default=0.5)
    parser.add_argument(
        "--stop-file", type=Path, default=Path("data/artifacts/ollama.resource-stop.json")
    )
    args = parser.parse_args()
    if args.sample_seconds != 0.5:
        raise SystemExit("sample-seconds must be 0.5 under current laptop policy")
    if args.stop_file.exists():
        raise SystemExit("Previous server resource stop is latched; remediation and pilot required")

    profile = PROFILES[ProfileName(args.profile)]
    try:
        preflight = observe_resources(host_monitor, gpu_monitor)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        raise SystemExit(
            f"RESOURCE_GUARD_REFUSED_START: monitor failure {type(exc).__name__}"
        ) from exc
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
    stop_reason = None
    next_sample = time.monotonic()
    try:
        while process.poll() is None:
            time.sleep(max(0, next_sample - time.monotonic()))
            next_sample = time.monotonic() + args.sample_seconds
            try:
                current = observe_resources(host_monitor, gpu_monitor)
            except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
                stop_reason = f"monitor failure {type(exc).__name__}"
                raise SystemExit(
                    f"RESOURCE_GUARD_STOP: monitor failure {type(exc).__name__}"
                ) from exc
            peak = merge_peak(peak, current)
            reason = unsafe_reason(current, profile.limits)
            if reason:
                stop_reason = reason
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
        print(json.dumps({"status": "stopped", "peak": peak.__dict__}, indent=2))
        return
    finally:
        try:
            stop_process_group(process)
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            stop_reason = stop_reason or f"cleanup failure {type(exc).__name__}"
        if stop_reason:
            args.stop_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.stop_file.with_suffix(args.stop_file.suffix + ".tmp")
            temporary.write_text(
                json.dumps({"reason": stop_reason, "observed_peak": peak.__dict__}, indent=2)
                + "\n",
                encoding="utf-8",
            )
            temporary.replace(args.stop_file)
            print(f"RESOURCE_GUARD_STOP latched at {args.stop_file}", flush=True)
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
