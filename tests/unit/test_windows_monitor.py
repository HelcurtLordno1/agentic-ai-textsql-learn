from __future__ import annotations

import io
import json
import time
from types import SimpleNamespace

import pytest

from agentic_text2sql.windows_monitor import WindowsHostMonitor


def test_monitor_accepts_bom_sample_but_rejects_closed_stream() -> None:
    monitor = WindowsHostMonitor()
    monitor.process = SimpleNamespace(
        stdout=io.StringIO(
            "\ufeff"
            + json.dumps(
                {"available_ram_gib": 20, "swap_used_gib": 0.1, "sampled_at_ms": time.time() * 1000}
            )
            + "\n"
        ),
        poll=lambda: None,
    )
    monitor._read()
    assert monitor.latest is not None and monitor.latest[:2] == (20, 0.1)
    with pytest.raises(ValueError, match="stdout closed"):
        monitor.sample()


@pytest.mark.parametrize(
    "line, reason",
    [
        ('{"available_ram_gib":20,"swap_used_gib":0,"sampled_at_ms":0}', "age_ms"),
        ('{"available_ram_gib":20}', "KeyError"),
        ("broken JSON", "JSONDecodeError"),
    ],
)
def test_sensor_protocol_errors_preserve_details_and_fail_closed(line: str, reason: str) -> None:
    monitor = WindowsHostMonitor()
    monitor.process = SimpleNamespace(stdout=io.StringIO(line), poll=lambda: None)
    monitor._read()
    with pytest.raises(ValueError, match=reason):
        monitor.sample()


def test_monitor_rejects_stale_sample_without_reusing_previous_safe_reading() -> None:
    monitor = WindowsHostMonitor()
    monitor.process = SimpleNamespace(poll=lambda: None)
    monitor.latest = (20, 0.1, time.monotonic() - 2)
    with pytest.raises(ValueError, match="stale: age_seconds"):
        monitor.sample()


def test_native_sensor_exit_includes_bounded_stderr() -> None:
    monitor = WindowsHostMonitor()
    monitor.process = SimpleNamespace(
        stderr=io.StringIO("x" * 5000 + "Pagefile sensor failed\n"), poll=lambda: 1
    )
    monitor._read_stderr()
    assert len(monitor.stderr_tail) == 4096
    with pytest.raises(ValueError, match="Pagefile sensor failed"):
        monitor.sample()


def test_initialization_can_take_six_seconds_but_still_requires_fresh_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elapsed = 0.0
    monitor = WindowsHostMonitor()
    monitor.process = SimpleNamespace(poll=lambda: None)

    def initialize(seconds: float) -> None:
        nonlocal elapsed
        elapsed += seconds
        if elapsed >= 6:
            monitor.latest = (20, 0.1, elapsed)

    monkeypatch.setattr(time, "monotonic", lambda: elapsed)
    monkeypatch.setattr(time, "sleep", initialize)
    monitor._wait_ready()
    assert 6 <= elapsed < 6.1
    assert monitor.sample() == (20, 0.1)
    elapsed += 1.1
    with pytest.raises(ValueError, match="stale"):
        monitor.sample()


def test_startup_never_proceeds_without_telemetry_and_reports_init_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elapsed = 0.0
    monitor = WindowsHostMonitor()
    monitor.process = SimpleNamespace(poll=lambda: None)
    monitor.stderr_tail = "WINDOWS MEMORY INIT: compiling native helper cache"

    def advance(seconds: float) -> None:
        nonlocal elapsed
        elapsed += seconds

    monkeypatch.setattr(time, "monotonic", lambda: elapsed)
    monkeypatch.setattr(time, "sleep", advance)
    with pytest.raises(ValueError, match=r"startup timeout after 15s;.*compiling native helper"):
        monitor._wait_ready()
    assert 15 <= elapsed < 15.1


def test_startup_monitor_error_is_immediate_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monitor = WindowsHostMonitor()
    monitor.process = SimpleNamespace(poll=lambda: None)
    monitor.error = "Windows memory helper cache checksum mismatch"
    monkeypatch.setattr(time, "sleep", lambda seconds: pytest.fail("retried a sensor failure"))
    with pytest.raises(ValueError, match="checksum mismatch"):
        monitor._wait_ready()
