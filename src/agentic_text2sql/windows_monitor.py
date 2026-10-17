"""Continuous Windows host RAM/pagefile telemetry for WSL model workloads."""

from __future__ import annotations

import json
import math
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from agentic_text2sql.clock import monotonic_seconds

STARTUP_TIMEOUT_SECONDS = 15
PROTOCOL = "text2sql-memory-rpc-v2"
RESPONSE_TIMEOUT_SECONDS = 1.0


class WindowsHostMonitor:
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.reader: threading.Thread | None = None
        self.stderr_reader: threading.Thread | None = None
        self.stderr_tail: str = ""
        self.latest: tuple[float, float, float] | None = None
        self.error: str | None = None
        self.lock = threading.Lock()
        self.sample_lock = threading.Lock()
        self.ready = False
        self.pending: tuple[str, float] | None = None
        self.completed_id: str | None = None
        self.maximum_roundtrip_seconds = 0.0

    def _accept(self, payload: Any) -> None:
        if not isinstance(payload, dict) or payload.get("protocol") != PROTOCOL:
            raise ValueError("Windows monitor protocol mismatch")
        if payload.get("kind") == "ready":
            with self.lock:
                if self.ready:
                    raise ValueError("Duplicate Windows monitor readiness")
                self.ready = True
            return
        if payload.get("kind") != "sample":
            raise ValueError("Unknown Windows monitor frame")
        ram, swap = float(payload["available_ram_gib"]), float(payload["swap_used_gib"])
        timestamp = float(payload["sampled_at_ms"])
        if not all(math.isfinite(value) and value >= 0 for value in (ram, swap, timestamp)):
            raise ValueError("Invalid Windows resource sample")
        if timestamp == 0:
            raise ValueError("Invalid Windows sample timestamp")
        now = monotonic_seconds()
        with self.lock:
            if self.pending is None or payload.get("request_id") != self.pending[0]:
                raise ValueError("Unsolicited, replayed or mismatched Windows sample")
            request_id, sent = self.pending
            elapsed = now - sent
            if not 0 <= elapsed <= RESPONSE_TIMEOUT_SECONDS:
                raise ValueError(f"Windows response is stale: roundtrip_seconds={elapsed}")
            self.latest = (ram, swap, now)
            self.completed_id = request_id
            self.pending = None
            self.maximum_roundtrip_seconds = max(self.maximum_roundtrip_seconds, elapsed)

    def _read(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        try:
            for line in process.stdout:
                payload: Any = json.loads(line.lstrip("\ufeff"))
                self._accept(payload)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            with self.lock:
                self.error = f"Windows monitor failed: {type(exc).__name__}: {exc}"
        finally:
            with self.lock:
                self.error = self.error or "Windows resource monitor stdout closed"

    def _read_stderr(self) -> None:
        process = self.process
        if process is not None and process.stderr is not None:
            for line in process.stderr:
                with self.lock:
                    self.stderr_tail = (self.stderr_tail + line)[-4096:]

    def __enter__(self) -> WindowsHostMonitor:
        script = Path(__file__).resolve().parents[2] / "scripts/windows_resource_monitor.ps1"
        windows_path = subprocess.check_output(
            ["wslpath", "-w", str(script)],
            text=True,
            timeout=2,
        ).strip()
        self.process = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                windows_path,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            start_new_session=True,
        )
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self.stderr_reader.start()
        try:
            self._wait_ready()
            return self
        except BaseException:
            self.close()
            raise

    def _wait_ready(self) -> None:
        # Initialization may compile/load the native helper. No workload starts
        # until a fresh sample exists; running sensor freshness stays at one second.
        deadline = monotonic_seconds() + STARTUP_TIMEOUT_SECONDS
        while monotonic_seconds() < deadline:
            with self.lock:
                ready, error = self.ready, self.error
            if error or ready or self.process is None or self.process.poll() is not None:
                self.sample()
                return
            time.sleep(0.05)
        with self.lock:
            stderr = self.stderr_tail.strip()
        raise ValueError(
            f"Windows resource monitor startup timeout after {STARTUP_TIMEOUT_SECONDS}s; "
            f"stderr={stderr}"
        )

    def sample(self) -> tuple[float, float]:
        if not self.sample_lock.acquire(blocking=False):
            raise ValueError("Concurrent Windows monitor requests are not allowed")
        try:
            self._alive()
            if not self.ready or self.process is None or self.process.stdin is None:
                raise ValueError("Windows monitor request channel is not ready")
            request_id = uuid.uuid4().hex
            sent = monotonic_seconds()
            with self.lock:
                self.pending = (request_id, sent)
                self.completed_id = None
            try:
                self.process.stdin.write(json.dumps({"request_id": request_id}) + "\n")
                self.process.stdin.flush()
            except OSError as exc:
                with self.lock:
                    self.error = f"Windows monitor request failed: {type(exc).__name__}"
                raise ValueError(self.error) from exc
            while True:
                self._alive()
                with self.lock:
                    if self.completed_id == request_id and self.latest is not None:
                        if monotonic_seconds() - sent > RESPONSE_TIMEOUT_SECONDS:
                            self.error = "Windows sample delivery exceeded one second"
                            raise ValueError(self.error)
                        return self.latest[:2]
                if monotonic_seconds() - sent >= RESPONSE_TIMEOUT_SECONDS:
                    with self.lock:
                        self.error = "Windows monitor response timeout after one second"
                    raise ValueError(self.error)
                time.sleep(0.01)
        finally:
            self.sample_lock.release()

    def _alive(self) -> None:
        with self.lock:
            error, stderr = self.error, self.stderr_tail
        if error or self.process is None or self.process.poll() is not None:
            raise ValueError(
                f"{error or 'Windows resource monitor is not running'}; stderr={stderr.strip()}"
            )

    def close(self) -> None:
        process = self.process
        if process is not None:
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except OSError:
                    pass  # A broken request pipe must not skip terminating the sensor.
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            if self.reader is not None:
                self.reader.join(timeout=1)
            if self.stderr_reader is not None:
                self.stderr_reader.join(timeout=1)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

    def __exit__(self, *_: object) -> None:
        self.close()
