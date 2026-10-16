from __future__ import annotations

import io
import json
import subprocess
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentic_text2sql import resource_guard
from agentic_text2sql.hardware import (
    PROFILES,
    ProfileName,
    ResourceLimits,
    ResourceSample,
    unsafe_reason,
)
from scripts import tmux_benchmarks


def test_failure_cleanup_keeps_native_heartbeat_through_entire_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elapsed = 0.0
    beats: list[float] = []

    class CoolingWorker:
        def poll(self) -> int | None:
            return 0 if elapsed >= 60 else None

        def wait(self, timeout: float) -> int:
            nonlocal elapsed
            elapsed += timeout
            if elapsed < 60:
                raise subprocess.TimeoutExpired("cooling", timeout)
            return 0

    monkeypatch.setattr(tmux_benchmarks.time, "monotonic", lambda: elapsed)
    tmux_benchmarks.wait_worker_cleanup(
        CoolingWorker(), SimpleNamespace(heartbeat=lambda: beats.append(elapsed))
    )
    assert len(beats) >= 300
    assert max(b - a for a, b in pairwise(beats)) < 0.3


def test_failure_cleanup_remains_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    elapsed = 0.0
    stopped = []

    class StuckWorker:
        def poll(self) -> None:
            return None

        def wait(self, timeout: float) -> int:
            nonlocal elapsed
            elapsed += timeout
            raise subprocess.TimeoutExpired("stuck", timeout)

    worker = StuckWorker()
    monkeypatch.setattr(tmux_benchmarks.time, "monotonic", lambda: elapsed)
    monkeypatch.setattr(tmux_benchmarks, "_stop", stopped.append)
    tmux_benchmarks.wait_worker_cleanup(worker, SimpleNamespace(heartbeat=lambda: None))
    assert elapsed == 200
    assert stopped == [worker]


def test_windows_host_pressure_is_not_hidden_by_free_wsl_ram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resource_guard, "sample_resources", lambda: ResourceSample(22, 0, 1000, 50, 30, 5, 800)
    )
    sample = resource_guard.observe_resources(SimpleNamespace(sample=lambda: (13, 0.3)))
    assert sample.available_ram_gib == 13
    assert sample.swap_used_gib == 0.3
    assert sample.windows_available_ram_gib == 13
    assert "RAM" in str(unsafe_reason(sample, ResourceLimits()))


def test_clock_monitor_rejects_missing_or_above_cap_and_merges_peak() -> None:
    limits = ResourceLimits(maximum_gpu_clock_mhz=800)
    assert "monitor failure" in str(unsafe_reason(ResourceSample(22, 0, 1000, 50, 30, 5), limits))
    assert "clock" in str(unsafe_reason(ResourceSample(22, 0, 1000, 50, 30, 5, 810), limits))
    peak = resource_guard.merge_peak(
        ResourceSample(22, 0, 1000, 50, 30, 5, 300, 20, 0),
        ResourceSample(19, 0, 1500, 53, 40, 30, 800, 18, 0.1),
    )
    assert peak.gpu_clock_mhz == 800
    assert peak.windows_available_ram_gib == 18
    assert peak.windows_swap_used_gib == 0.1


def test_native_resource_stop_requires_cleanup_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    monkeypatch.setattr(tmux_benchmarks, "directory", lambda plan: tmp_path)
    owner = tmux_benchmarks.OwnedServer(SimpleNamespace(), io.StringIO())
    owner.process = SimpleNamespace(poll=lambda: 1, returncode=1)
    latch = tmp_path / "server.resource-stop.json"
    latch.write_text(json.dumps({"reason": "VRAM", "cleanup_complete": True}))
    owner.close()
    with pytest.raises(ValueError, match=r"VRAM.*no automatic retry"):
        tmux_benchmarks.ensure_no_latch(SimpleNamespace(benchmarks=[]))
    latch.write_text(json.dumps({"reason": "VRAM", "cleanup_complete": False}))
    with pytest.raises(ValueError, match="cleanup unverified"):
        owner.close()


def test_user_authorized_full_gpu_keeps_headroom_and_thermal_clock_guard() -> None:
    profile = PROFILES[ProfileName.QWEN_FULL_GPU]
    assert profile.ollama_num_gpu == 41
    assert unsafe_reason(ResourceSample(12, 0, 11500, 60, 60, 99, 450), profile.limits) is None
    for sample, marker in (
        (ResourceSample(7.9, 0, 11500, 60, 60, 99, 450), "RAM"),
        (ResourceSample(12, 0, 14336, 60, 60, 99, 450), "VRAM"),
        (ResourceSample(12, 0, 11500, 68, 60, 99, 450), "temperature"),
        (ResourceSample(12, 0, 11500, 60, 70, 99, 450), "power"),
        (ResourceSample(12, 0, 11500, 60, 60, 99, 465), "clock"),
    ):
        assert marker in str(unsafe_reason(sample, profile.limits))
    assert PROFILES[ProfileName.ACCEPTANCE].limits.maximum_gpu_memory_mib == 6144
