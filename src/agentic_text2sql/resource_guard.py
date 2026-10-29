"""Fail-closed process watchdog shared by all local-model entrypoints."""

from __future__ import annotations

import fcntl
import json
import os
import signal
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from tempfile import gettempdir
from typing import Any

import httpx

from agentic_text2sql.clock import monotonic_seconds, sleep_seconds
from agentic_text2sql.gpu_monitor import GpuMonitor
from agentic_text2sql.hardware import (
    ResourceLimits,
    ResourceSample,
    sample_resources,
    unsafe_reason,
)
from agentic_text2sql.windows_monitor import WindowsHostMonitor


class ResourceGuardError(RuntimeError):
    pass


@contextmanager
def workload_lease(path: Path) -> Iterator[None]:
    """Hold an exclusive local workload lease, including its cooldown."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ResourceGuardError("Another guarded local workload is active") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def unload_models(base_url: str) -> None:
    """Unload every resident model, including specialist models with custom names."""
    with httpx.Client(base_url=base_url, timeout=10) as client:
        response = client.get("/api/ps")
        response.raise_for_status()
        models = response.json().get("models")
        if not isinstance(models, list):
            raise ResourceGuardError("Cannot enumerate resident Ollama models for cleanup")
        for model in models:
            name = model.get("name") if isinstance(model, dict) else None
            if not isinstance(name, str):
                raise ResourceGuardError("Invalid resident model identity")
            client.post(
                "/api/generate", json={"model": name, "prompt": "", "keep_alive": 0}
            ).raise_for_status()


def merge_peak(previous: ResourceSample, current: ResourceSample) -> ResourceSample:
    def minimum(a: float | None, b: float | None) -> float | None:
        return b if a is None else a if b is None else min(a, b)

    def maximum(a: float | None, b: float | None) -> float | None:
        return b if a is None else a if b is None else max(a, b)

    clocks = [
        value for value in (previous.gpu_clock_mhz, current.gpu_clock_mhz) if value is not None
    ]
    return ResourceSample(
        min(previous.available_ram_gib, current.available_ram_gib),
        max(previous.swap_used_gib, current.swap_used_gib),
        max(previous.gpu_memory_mib, current.gpu_memory_mib),
        max(previous.gpu_temperature_c, current.gpu_temperature_c),
        max(previous.gpu_power_w, current.gpu_power_w),
        max(previous.gpu_utilization_pct, current.gpu_utilization_pct),
        max(clocks) if clocks else None,
        minimum(previous.windows_available_ram_gib, current.windows_available_ram_gib),
        maximum(previous.windows_swap_used_gib, current.windows_swap_used_gib),
    )


def observe_resources(
    host_monitor: WindowsHostMonitor | None = None, gpu_monitor: GpuMonitor | None = None
) -> ResourceSample:
    observation = sample_resources(gpu_monitor.sample()) if gpu_monitor else sample_resources()
    if host_monitor is None:
        return observation
    ram, swap = host_monitor.sample()
    return replace(
        observation,
        available_ram_gib=min(observation.available_ram_gib, ram),
        swap_used_gib=max(observation.swap_used_gib, swap),
        windows_available_ram_gib=ram,
        windows_swap_used_gib=swap,
    )


def _stop(process: subprocess.Popen[bytes]) -> None:
    for sig, wait in ((signal.SIGINT, 2), (signal.SIGTERM, 2), (signal.SIGKILL, 2)):
        try:
            # uv may exit before its Python worker. Stop the owned group even
            # when the group leader already has a return code.
            os.killpg(process.pid, sig)
            deadline = monotonic_seconds() + wait
            while monotonic_seconds() < deadline:
                process.poll()  # Reap the leader so it does not keep the group alive.
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    return
                sleep_seconds(0.05)
        except ProcessLookupError:
            return
    raise ResourceGuardError("Child process did not terminate after SIGKILL")


def guarded_process(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    base_url: str,
    stop_path: Path,
    limits: ResourceLimits | None = None,
    sample_interval: float = 0.5,
    cooldown_seconds: float = 0,
    on_spawn: Callable[[int], None] | None = None,
    on_cooldown: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    if cooldown_seconds < 0:
        raise ValueError("cooldown_seconds must be nonnegative")
    lease = Path(gettempdir()) / f"agentic-text2sql-{os.getuid()}.workload.lock"
    with workload_lease(lease):
        try:
            return _guarded_process(
                command,
                cwd=cwd,
                environment=environment,
                base_url=base_url,
                stop_path=stop_path,
                limits=limits,
                sample_interval=sample_interval,
                on_spawn=on_spawn,
            )
        finally:
            # Keep the lease through cooldown, including a failed workload. A
            # resource latch remains intact; cooling never authorizes a retry.
            if cooldown_seconds:
                try:
                    if on_cooldown is not None:
                        on_cooldown(time.time() + cooldown_seconds)
                finally:
                    sleep_seconds(cooldown_seconds)


def _guarded_process(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    base_url: str,
    stop_path: Path,
    limits: ResourceLimits | None,
    sample_interval: float,
    on_spawn: Callable[[int], None] | None,
) -> dict[str, Any]:
    """Check before spawn and continuously; any breach stops without retry."""
    if not 0 < sample_interval <= 0.5:
        raise ValueError("sampling interval must be positive and at most 0.5 seconds")
    if stop_path.exists():
        raise ResourceGuardError(
            "Previous resource-stop latch exists; remediation and pilot required"
        )
    limits = limits or ResourceLimits()
    process: subprocess.Popen[bytes] | None = None
    peak: ResourceSample | None = None
    reason: str | None = None
    cleanup_error: str | None = None
    samples = 0
    resource_stop = False
    host_monitor = (
        WindowsHostMonitor()
        if environment.get("TEXT2SQL_MONITOR_WINDOWS_HOST", "").lower() == "true"
        else None
    )
    gpu_monitor = GpuMonitor()
    gpu_monitor.journal_path = stop_path.with_suffix(".gpu-raw.jsonl")
    try:
        try:
            if host_monitor is not None:
                host_monitor.__enter__()
            gpu_monitor.__enter__()
            peak = observe_resources(host_monitor, gpu_monitor)
            samples += 1
            reason = unsafe_reason(peak, limits)
        except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
            reason = f"monitor failure: {type(exc).__name__}: {exc}"
        if reason:
            resource_stop = True
            raise ResourceGuardError(reason)
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env={**environment, "TEXT2SQL_GUARDED_RUN": "true"},
            start_new_session=True,
        )
        if on_spawn is not None:
            on_spawn(process.pid)
        while process.poll() is None:
            observation_started = monotonic_seconds()
            try:
                current = observe_resources(host_monitor, gpu_monitor)
                samples += 1
                peak = merge_peak(peak, current) if peak else current
                reason = unsafe_reason(current, limits)
            except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
                reason = f"monitor failure: {type(exc).__name__}: {exc}"
            if reason:
                resource_stop = True
                raise ResourceGuardError(reason)
            sleep_seconds(max(0, sample_interval - (monotonic_seconds() - observation_started)))
        # Even a short child gets a final observation; it cannot mask a breach.
        try:
            current = observe_resources(host_monitor, gpu_monitor)
            samples += 1
            peak = merge_peak(peak, current) if peak else current
            reason = unsafe_reason(current, limits)
        except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
            reason = f"monitor failure: {type(exc).__name__}: {exc}"
        if reason:
            resource_stop = True
            raise ResourceGuardError(reason)
        if process.returncode:
            raise ResourceGuardError(f"guarded child exited {process.returncode}")
    except BaseException as exc:
        reason = reason or f"guarded workload stopped: {type(exc).__name__}: {exc}"
        raise
    finally:
        if process is not None:
            try:
                _stop(process)
            except (OSError, subprocess.SubprocessError, ResourceGuardError) as exc:
                cleanup_error = f"child stop failed: {type(exc).__name__}"
        try:
            unload_models(base_url)
        except (httpx.HTTPError, ValueError, ResourceGuardError) as exc:
            cleanup_error = (cleanup_error or "") + f" model unload failed: {type(exc).__name__}"
        if host_monitor is not None:
            try:
                host_monitor.close()
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                cleanup_error = (
                    cleanup_error or ""
                ) + f" host monitor stop failed: {type(exc).__name__}"
        try:
            gpu_monitor.close()
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            cleanup_error = (
                cleanup_error or ""
            ) + f" GPU monitor stop failed: {type(exc).__name__}"
        summary = {
            "reason": reason,
            "observed_peak": asdict(peak) if peak else None,
            "samples": samples,
            "sample_interval_seconds": sample_interval,
            "cleanup_error": cleanup_error,
            "limits": limits.model_dump(mode="json"),
            "resource_stop": resource_stop or bool(cleanup_error),
        }
        journal = stop_path.with_suffix(".samples.jsonl")
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(summary) + "\n")
        if reason or cleanup_error:
            record_path = (
                stop_path
                if resource_stop or cleanup_error
                else stop_path.with_suffix(".workload-error.json")
            )
            record_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = record_path.with_suffix(record_path.suffix + ".tmp")
            temporary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
            temporary.replace(record_path)
            status = "RESOURCE_GUARD_STOP" if resource_stop or cleanup_error else "WORKLOAD_STOP"
            print(json.dumps({"status": status, **summary}), flush=True)
        if cleanup_error and reason is None:
            raise ResourceGuardError(cleanup_error)
    return summary
