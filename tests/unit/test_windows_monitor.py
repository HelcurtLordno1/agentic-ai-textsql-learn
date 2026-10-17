from __future__ import annotations

import io
import json
from types import SimpleNamespace
from typing import Any

import pytest

from agentic_text2sql import windows_monitor as wm
from agentic_text2sql.windows_monitor import PROTOCOL, WindowsHostMonitor


def response(request_id: str, **changes: Any) -> dict[str, Any]:
    return {
        "protocol": PROTOCOL,
        "kind": "sample",
        "request_id": request_id,
        "available_ram_gib": 20,
        "swap_used_gib": 0.1,
        "sampled_at_ms": 123456,
        **changes,
    }


def ready_monitor(callback: Any) -> WindowsHostMonitor:
    monitor = WindowsHostMonitor()

    class Input:
        def write(self, line: str) -> None:
            callback(monitor, json.loads(line)["request_id"])

        def flush(self) -> None:
            pass

    monitor.process = SimpleNamespace(stdin=Input(), poll=lambda: None)
    monitor.ready = True
    return monitor


@pytest.mark.parametrize("timestamp", [1, 9999999999999])
def test_fresh_nonce_response_accepts_unsynchronized_host_clock(timestamp: int) -> None:
    monitor = ready_monitor(lambda m, key: m._accept(response(key, sampled_at_ms=timestamp)))
    assert monitor.sample() == (20, 0.1)
    assert monitor.maximum_roundtrip_seconds < 1


def test_monitor_accepts_bom_sample_but_rejects_closed_stream() -> None:
    monitor = WindowsHostMonitor()
    monitor.pending = ("nonce", wm.monotonic_seconds())
    monitor.process = SimpleNamespace(
        stdout=io.StringIO("\ufeff" + json.dumps(response("nonce")) + "\n"), poll=lambda: None
    )
    monitor._read()
    assert monitor.latest is not None and monitor.latest[:2] == (20, 0.1)
    with pytest.raises(ValueError, match="stdout closed"):
        monitor.sample()


@pytest.mark.parametrize(
    "payload,reason",
    [
        (response("nonce", sampled_at_ms=0), "Invalid Windows sample timestamp"),
        (response("nonce", available_ram_gib=float("nan")), "Invalid Windows resource sample"),
        ({"protocol": PROTOCOL, "kind": "sample"}, "KeyError"),
        ({"protocol": "old"}, "protocol mismatch"),
        ("broken JSON", "JSONDecodeError"),
    ],
)
def test_sensor_protocol_errors_fail_closed(payload: Any, reason: str) -> None:
    monitor = WindowsHostMonitor()
    line = payload if isinstance(payload, str) else json.dumps(payload)
    monitor.process = SimpleNamespace(stdout=io.StringIO(line), poll=lambda: None)
    monitor._read()
    with pytest.raises(ValueError, match=reason):
        monitor.sample()


def test_replayed_or_wrong_nonce_is_rejected() -> None:
    monitor = ready_monitor(lambda m, key: m._accept(response(key)))
    monitor.sample()
    with pytest.raises(ValueError, match="replayed"):
        monitor._accept(response(monitor.completed_id or ""))
    monitor.pending = ("expected", wm.monotonic_seconds())
    with pytest.raises(ValueError, match="mismatched"):
        monitor._accept(response("different"))


def test_late_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monitor = WindowsHostMonitor()
    monitor.pending = ("nonce", 0)
    monkeypatch.setattr(wm, "monotonic_seconds", lambda: 1.001)
    with pytest.raises(ValueError, match="roundtrip_seconds"):
        monitor._accept(response("nonce"))


def test_timeout_never_reuses_cached_safe_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    elapsed = 0.0

    def advance(seconds: float) -> None:
        nonlocal elapsed
        elapsed += seconds

    monitor = ready_monitor(lambda m, key: None)
    monitor.latest = (20, 0.1, 0)
    monkeypatch.setattr(wm, "monotonic_seconds", lambda: elapsed)
    monkeypatch.setattr(wm.time, "sleep", advance)
    with pytest.raises(ValueError, match="response timeout"):
        monitor.sample()
    assert 1 <= elapsed < 1.02
    with pytest.raises(ValueError, match="response timeout"):
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


def test_initialization_can_take_six_seconds_but_requires_fresh_rpc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elapsed = 0.0
    monitor = ready_monitor(lambda m, key: m._accept(response(key)))
    monitor.ready = False

    def initialize(seconds: float) -> None:
        nonlocal elapsed
        elapsed += seconds
        if elapsed >= 6:
            monitor.ready = True

    monkeypatch.setattr(wm, "monotonic_seconds", lambda: elapsed)
    monkeypatch.setattr(wm.time, "sleep", initialize)
    monitor._wait_ready()
    assert 6 <= elapsed < 6.1
    assert monitor.completed_id is not None


def test_startup_never_proceeds_without_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    elapsed = 0.0
    monitor = WindowsHostMonitor()
    monitor.process = SimpleNamespace(poll=lambda: None)
    monitor.stderr_tail = "WINDOWS MEMORY INIT: compiling native helper cache"

    def advance(seconds: float) -> None:
        nonlocal elapsed
        elapsed += seconds

    monkeypatch.setattr(wm, "monotonic_seconds", lambda: elapsed)
    monkeypatch.setattr(wm.time, "sleep", advance)
    with pytest.raises(ValueError, match=r"startup timeout after 15s;.*compiling native helper"):
        monitor._wait_ready()
    assert 15 <= elapsed < 15.1


def test_startup_monitor_error_is_immediate_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monitor = WindowsHostMonitor()
    monitor.process = SimpleNamespace(poll=lambda: None)
    monitor.error = "Windows memory helper cache checksum mismatch"
    monkeypatch.setattr(wm.time, "sleep", lambda seconds: pytest.fail("retried a sensor failure"))
    with pytest.raises(ValueError, match="checksum mismatch"):
        monitor._wait_ready()
