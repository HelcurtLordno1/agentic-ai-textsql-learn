"""Continuous Windows host RAM/pagefile telemetry for WSL model workloads."""

from __future__ import annotations

import json
import math
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

STARTUP_TIMEOUT_SECONDS = 15


class WindowsHostMonitor:
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.reader: threading.Thread | None = None
        self.stderr_reader: threading.Thread | None = None
        self.stderr_tail: str = ""
        self.latest: tuple[float, float, float] | None = None
        self.error: str | None = None
        self.lock = threading.Lock()

    def _read(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        try:
            for line in process.stdout:
                payload: Any = json.loads(line.lstrip("\ufeff"))
                ram = float(payload["available_ram_gib"])
                swap = float(payload["swap_used_gib"])
                sampled_at_ms = float(payload["sampled_at_ms"])
                if (
                    not math.isfinite(sampled_at_ms)
                    or abs(time.time() * 1000 - sampled_at_ms) > 1000
                ):
                    raise ValueError(
                        "Windows sensor data is stale or host clocks differ: "
                        f"age_ms={time.time() * 1000 - sampled_at_ms:.0f}"
                    )
                if not all(math.isfinite(value) and value >= 0 for value in (ram, swap)):
                    raise ValueError("Invalid Windows resource sample")
                with self.lock:
                    self.latest = (ram, swap, time.monotonic())
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
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            with self.lock:
                ready, error = self.latest is not None, self.error
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
        with self.lock:
            record, error, stderr = self.latest, self.error, self.stderr_tail
        if error or self.process is None or self.process.poll() is not None:
            raise ValueError(
                f"{error or 'Windows resource monitor is not running'}; stderr={stderr.strip()}"
            )
        if record is None or time.monotonic() - record[2] > 1:
            age = time.monotonic() - record[2] if record else None
            raise ValueError(f"Windows resource monitor is stale: age_seconds={age}")
        return record[0], record[1]

    def close(self) -> None:
        process = self.process
        if process is not None:
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
