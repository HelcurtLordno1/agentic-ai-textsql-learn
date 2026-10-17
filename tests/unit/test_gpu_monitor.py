from __future__ import annotations

import io
import subprocess
import sys
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from agentic_text2sql import gpu_monitor as gm
from agentic_text2sql.gpu_monitor import GpuMonitor
from agentic_text2sql.hardware import ResourceLimits, parse_gpu_sample, unsafe_reason

SAFE = "1000, 45, 18.0, 19.0, 0, 300\n"


def prepared() -> GpuMonitor:
    sensor = GpuMonitor()
    sensor.process = SimpleNamespace(poll=lambda: None)
    return sensor


def test_intermediate_power_peak_survives_a_later_safe_frame() -> None:
    sensor = prepared()
    sensor._accept(SAFE)
    sensor._accept("1100, 46, 20, 73.4, 99, 600\n")
    sensor._accept(SAFE)
    observation = sensor.sample()
    assert observation.gpu_power_w == 73.4
    assert observation.gpu_memory_mib == 1100 and observation.gpu_clock_mhz == 600
    assert "GPU power" in str(
        unsafe_reason(replace(observation, available_ram_gib=20), ResourceLimits())
    )
    sensor._accept(SAFE)
    assert sensor.sample().gpu_power_w == 19


@pytest.mark.parametrize(
    "line",
    [
        "",
        "GPU has fallen off the bus",
        SAFE + SAFE,
        "1000, 45, NaN, 19, 0, 300",
        "1000, 45, 18, inf, 0, 300",
        "1000, 45, 18, 19, 101, 300",
        "1000, 45, 18, 19, -1, 300",
        "1000, 45, 18, 19, 0, 300.5",
    ],
)
def test_bad_sensor_frames_are_never_accepted(line: str) -> None:
    with pytest.raises(ValueError):
        parse_gpu_sample(line)


def test_stale_and_late_stream_cannot_be_revived_by_a_new_safe_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 10.0
    monkeypatch.setattr(gm, "monotonic_seconds", lambda: now)
    sensor = prepared()
    sensor._accept(SAFE)
    now += 0.501
    with pytest.raises(ValueError, match="stale"):
        sensor.sample()
    # The latched error is not cleared by a subsequently arriving frame.
    with pytest.raises(ValueError, match="sampling gap"):
        sensor._accept(SAFE)
    with pytest.raises(ValueError, match="stale"):
        sensor.sample()


def test_stdout_error_is_permanent_and_includes_bounded_stderr() -> None:
    sensor = prepared()
    sensor.process.stdout = io.StringIO(SAFE + "NVIDIA-SMI failed\n")
    sensor.process.stderr = io.StringIO("x" * 6000 + "driver unavailable\n")
    sensor._read_stderr()
    sensor._read()
    assert len(sensor.stderr_tail) == 4096
    with pytest.raises(ValueError, match="driver unavailable"):
        sensor.sample()


def test_startup_is_bounded_without_a_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 0.0
    sensor = prepared()

    def advance(seconds: float) -> None:
        nonlocal now
        now += seconds

    monkeypatch.setattr(gm, "monotonic_seconds", lambda: now)
    monkeypatch.setattr(gm, "sleep_seconds", advance)
    with pytest.raises(ValueError, match="startup timeout"):
        sensor._wait_initial()
    assert 5 <= now < 5.02


def test_consumed_sample_is_never_reused_when_stream_freezes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 0.0
    sensor = prepared()

    def advance(seconds: float) -> None:
        nonlocal now
        now += seconds

    monkeypatch.setattr(gm, "monotonic_seconds", lambda: now)
    monkeypatch.setattr(gm, "sleep_seconds", advance)
    sensor._accept(SAFE)
    sensor.sample()
    with pytest.raises(ValueError, match=r"stale|response timeout"):
        sensor.sample()
    assert 0.5 <= now < 0.51


def test_one_process_handles_multiple_reads_and_closes_on_context_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spawn = subprocess.Popen
    processes = []

    def fake_sensor(command, **kwargs):
        assert "--loop-ms=200" in command
        # A delayed initialization formerly exceeded the per-process 0.5s deadline.
        code = (
            "import time\ntime.sleep(.6)\nwhile True:\n print('"
            + SAFE.strip()
            + "', flush=True)\n time.sleep(.05)"
        )
        process = spawn([sys.executable, "-u", "-c", code], **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(gm.subprocess, "Popen", fake_sensor)
    with GpuMonitor() as sensor:
        for _ in range(4):
            assert sensor.sample().gpu_power_w == 19
            time.sleep(0.03)
    assert len(processes) == 1 and processes[0].poll() is not None
    assert sensor.reader is not None and not sensor.reader.is_alive()


def test_startup_failure_terminates_the_owned_sensor(monkeypatch: pytest.MonkeyPatch) -> None:
    spawn = subprocess.Popen
    processes = []

    def broken_sensor(command, **kwargs):
        process = spawn(
            [sys.executable, "-u", "-c", "print('invalid',flush=True);import time;time.sleep(30)"],
            **kwargs,
        )
        processes.append(process)
        return process

    monkeypatch.setattr(gm.subprocess, "Popen", broken_sensor)
    with pytest.raises(ValueError, match="GPU stream failed"):
        with GpuMonitor():
            pytest.fail("A broken sensor permitted startup")
    assert len(processes) == 1 and processes[0].poll() is not None


@pytest.mark.parametrize("during_work", [False, True])
def test_sensor_failure_latches_guard_and_cleans_owned_processes(
    tmp_path, monkeypatch: pytest.MonkeyPatch, during_work: bool
) -> None:
    from agentic_text2sql import resource_guard as guard

    events = []

    class Sensor:
        calls = 0

        def __enter__(self):
            if not during_work:
                raise ValueError("sensor startup failed")
            return self

        def sample(self):
            self.calls += 1
            if self.calls > 1:
                raise ValueError("GPU sensor stream sample stale")
            return parse_gpu_sample(SAFE)

        def close(self):
            events.append("sensor_closed")

    def spawn(*args, **kwargs):
        if not during_work:
            pytest.fail("Workload spawned without a working sensor")
        return SimpleNamespace(poll=lambda: None)

    monkeypatch.setattr(guard, "GpuMonitor", Sensor)
    monkeypatch.setattr(guard, "sample_resources", lambda gpu: replace(gpu, available_ram_gib=20))
    monkeypatch.setattr(guard.subprocess, "Popen", spawn)
    monkeypatch.setattr(guard, "_stop", lambda child: events.append("child_stopped"))
    monkeypatch.setattr(guard, "unload_models", lambda url: events.append("models_unloaded"))
    stop = tmp_path / "stop.json"
    with pytest.raises(guard.ResourceGuardError, match="monitor failure"):
        guard.guarded_process(
            ["unused"], cwd=tmp_path, environment={}, base_url="http://test", stop_path=stop
        )
    assert stop.exists()
    assert "sensor_closed" in events and "models_unloaded" in events
    assert ("child_stopped" in events) == during_work
