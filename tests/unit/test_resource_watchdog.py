from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agentic_text2sql import resource_guard
from agentic_text2sql.hardware import ResourceLimits, ResourceSample, unsafe_reason
from agentic_text2sql.resource_guard import ResourceGuardError, guarded_process

SAFE = ResourceSample(15, 0, 3000, 60, 40, 10)


@pytest.fixture(autouse=True)
def mocked_gpu_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    # These tests inject the resource observations; GPU transport has its own tests.
    observe = resource_guard.observe_resources
    monkeypatch.setattr(
        resource_guard, "observe_resources", lambda host=None, gpu=None: observe(host)
    )
    monkeypatch.setattr(
        resource_guard,
        "GpuMonitor",
        lambda: SimpleNamespace(__enter__=lambda: None, close=lambda: None),
    )


def test_watchdog_preflight_breach_never_starts_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        resource_guard, "sample_resources", lambda: ResourceSample(13, 0, 3000, 60, 40, 10)
    )
    monkeypatch.setattr(
        resource_guard.subprocess, "Popen", lambda *a, **k: pytest.fail("unsafe child spawn")
    )
    unloaded = []
    monkeypatch.setattr(resource_guard, "unload_models", lambda url: unloaded.append(url))
    stop = tmp_path / "stop.json"
    with pytest.raises(ResourceGuardError, match="RAM"):
        guarded_process(
            ["unused"], cwd=tmp_path, environment={}, base_url="http://test", stop_path=stop
        )
    assert unloaded == ["http://test"]
    assert json.loads(stop.read_text())["samples"] == 1


def test_watchdog_monitor_failure_during_work_stops_and_unloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    count = 0
    stopped = []
    unloaded = []

    def sample() -> ResourceSample:
        nonlocal count
        count += 1
        if count == 1:
            return SAFE
        raise ValueError("sensor unavailable")

    class Child:
        def poll(self) -> None:
            return None

    monkeypatch.setattr(resource_guard, "sample_resources", sample)
    monkeypatch.setattr(resource_guard.subprocess, "Popen", lambda *a, **k: Child())
    monkeypatch.setattr(resource_guard, "_stop", lambda child: stopped.append(child))
    monkeypatch.setattr(resource_guard, "unload_models", lambda url: unloaded.append(url))
    stop = tmp_path / "stop.json"
    with pytest.raises(ResourceGuardError, match="monitor failure"):
        guarded_process(
            ["unused"], cwd=tmp_path, environment={}, base_url="http://test", stop_path=stop
        )
    assert len(stopped) == len(unloaded) == 1
    assert json.loads(stop.read_text())["reason"] == (
        "monitor failure: ValueError: sensor unavailable"
    )
    assert json.loads(stop.read_text())["observed_peak"]["gpu_power_w"] == 40
    # No auto-resume, and no new child spawned when a previous stop is latched.
    with pytest.raises(ResourceGuardError, match="latch"):
        guarded_process(
            ["unused"], cwd=tmp_path, environment={}, base_url="http://test", stop_path=stop
        )
    assert count == 2


def test_watchdog_observes_mid_run_breach_and_preserves_peak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = iter([SAFE, SAFE, ResourceSample(15, 0, 3000, 68, 70, 100)])
    monkeypatch.setattr(resource_guard, "sample_resources", lambda: next(values))

    class Child:
        def poll(self) -> None:
            return None

    monkeypatch.setattr(resource_guard.subprocess, "Popen", lambda *a, **k: Child())
    monkeypatch.setattr(resource_guard, "_stop", lambda child: None)
    monkeypatch.setattr(resource_guard, "unload_models", lambda url: None)
    monkeypatch.setattr(resource_guard, "sleep_seconds", lambda seconds: None)
    stop = tmp_path / "stop.json"
    with pytest.raises(ResourceGuardError):
        guarded_process(
            ["unused"], cwd=tmp_path, environment={}, base_url="http://test", stop_path=stop
        )
    payload = json.loads(stop.read_text())
    assert payload["samples"] == 3
    assert payload["observed_peak"]["gpu_temperature_c"] == 68
    assert payload["observed_peak"]["gpu_power_w"] == 70


def test_short_child_gets_final_sample_and_guard_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    class Child:
        returncode = 0

        def poll(self) -> int:
            return 0

    def spawn(*args: Any, **kwargs: Any) -> Child:
        calls.append(kwargs)
        return Child()

    monkeypatch.setattr(resource_guard, "sample_resources", lambda: SAFE)
    monkeypatch.setattr(resource_guard.subprocess, "Popen", spawn)
    monkeypatch.setattr(resource_guard, "_stop", lambda child: None)
    monkeypatch.setattr(resource_guard, "unload_models", lambda url: None)
    result = guarded_process(
        ["unused"],
        cwd=tmp_path,
        environment={},
        base_url="http://test",
        stop_path=tmp_path / "stop.json",
    )
    assert result["samples"] == 2
    assert calls[0]["env"]["TEXT2SQL_GUARDED_RUN"] == "true"
    assert calls[0]["start_new_session"] is True


@pytest.mark.parametrize(
    "sample",
    [ResourceSample(15, 0, 3000, 60, float("nan"), 0), ResourceSample(15, 0, 3000, 60, 40, 101)],
)
def test_nonfinite_and_invalid_monitor_metrics_fail_closed(sample: ResourceSample) -> None:
    assert "monitor failure" in str(unsafe_reason(sample, ResourceLimits()))


def test_workload_lease_refuses_concurrent_guard_and_releases_after_exit(tmp_path: Path) -> None:
    path = tmp_path / "lease.lock"
    with resource_guard.workload_lease(path):
        with pytest.raises(ResourceGuardError, match="Another guarded"):
            with resource_guard.workload_lease(path):
                pytest.fail("A second workload acquired an occupied lease")
    with resource_guard.workload_lease(path):
        pass


def test_ordinary_child_failure_is_not_a_hardware_latch_and_still_cools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Child:
        pid = 12345
        returncode = 2

        def poll(self) -> int:
            return self.returncode

    monkeypatch.setattr(resource_guard, "sample_resources", lambda: SAFE)
    monkeypatch.setattr(resource_guard.subprocess, "Popen", lambda *a, **k: Child())
    monkeypatch.setattr(resource_guard, "_stop", lambda child: None)
    monkeypatch.setattr(resource_guard, "unload_models", lambda url: None)
    sleeps = []
    spawned = []
    deadlines = []
    monkeypatch.setattr(resource_guard, "sleep_seconds", sleeps.append)
    stop = tmp_path / "stop.json"
    with pytest.raises(ResourceGuardError, match="child exited 2"):
        guarded_process(
            ["unused"],
            cwd=tmp_path,
            environment={},
            base_url="http://test",
            stop_path=stop,
            cooldown_seconds=60,
            on_spawn=spawned.append,
            on_cooldown=deadlines.append,
        )
    assert not stop.exists()
    assert stop.with_suffix(".workload-error.json").exists()
    assert spawned == [12345] and len(deadlines) == 1 and sleeps == [60]
