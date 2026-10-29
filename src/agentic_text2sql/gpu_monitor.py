"""One owned GPU sensor stream; no process launch on the hot sampling path."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import TextIO

from agentic_text2sql.clock import monotonic_seconds, sleep_seconds
from agentic_text2sql.hardware import ResourceSample, parse_gpu_sample

STARTUP_SECONDS = 5.0
FRESH_SECONDS = 0.5
GPU_QUERY = (
    "--query-gpu=memory.used,temperature.gpu,power.draw.average,power.draw.instant,"
    "utilization.gpu,clocks.current.graphics"
)


class GpuMonitor:
    def __init__(self) -> None:
        self.journal_path: Path | None = None
        self.journal: TextIO | None = None
        self.process: subprocess.Popen[str] | None = None
        self.reader: threading.Thread | None = None
        self.stderr_reader: threading.Thread | None = None
        self.lock = threading.Lock()
        self.latest_at: float | None = None
        self.pending: ResourceSample | None = None
        self.error: str | None = None
        self.stderr_tail = ""
        self.closing = False

    def _accept(self, line: str) -> None:
        sample = parse_gpu_sample(line)
        now = monotonic_seconds()
        if self.journal is not None:
            parts = line.strip().split(",")
            self.journal.write(
                json.dumps(
                    {
                        "received_at_ms": time.time_ns() // 1_000_000,
                        "received_monotonic_seconds": now,
                        "raw": line.strip(),
                        "power_average_w": float(parts[2]),
                        "power_instant_w": float(parts[3]),
                        "source": "wsl-nvidia-smi",
                    }
                )
                + "\n"
            )
            self.journal.flush()
        with self.lock:
            if self.latest_at is not None and now - self.latest_at > FRESH_SECONDS:
                raise ValueError("GPU stream sampling gap exceeded 0.5 seconds")
            previous = self.pending
            # Retain every observed peak until the guard consumes it. A safe
            # later frame must not erase an intermediate unsafe observation.
            self.pending = (
                replace(
                    sample,
                    gpu_memory_mib=max(previous.gpu_memory_mib, sample.gpu_memory_mib),
                    gpu_temperature_c=max(previous.gpu_temperature_c, sample.gpu_temperature_c),
                    gpu_power_w=max(previous.gpu_power_w, sample.gpu_power_w),
                    gpu_utilization_pct=max(
                        previous.gpu_utilization_pct, sample.gpu_utilization_pct
                    ),
                    gpu_clock_mhz=max(previous.gpu_clock_mhz or 0, sample.gpu_clock_mhz or 0),
                )
                if previous is not None
                else sample
            )
            self.latest_at = now

    def _read(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            for line in self.process.stdout:
                self._accept(line)
        except (OSError, ValueError) as exc:
            with self.lock:
                self.error = f"GPU stream failed: {type(exc).__name__}: {exc}"
        finally:
            with self.lock:
                if not self.closing:
                    self.error = self.error or "GPU sensor stream stdout closed"

    def _read_stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        for line in self.process.stderr:
            with self.lock:
                self.stderr_tail = (self.stderr_tail + line)[-4096:]

    def __enter__(self) -> GpuMonitor:
        if self.journal_path is not None:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            self.journal = self.journal_path.open("a", encoding="utf-8")
        self.process = subprocess.Popen(
            ["nvidia-smi", "--id=0", GPU_QUERY, "--format=csv,noheader,nounits", "--loop-ms=200"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            start_new_session=True,
        )
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self.reader.start()
        self.stderr_reader.start()
        try:
            self._wait_initial()
            return self
        except BaseException:
            self.close()
            raise

    def _alive(self) -> None:
        if self.error or self.process is None or self.process.poll() is not None:
            raise ValueError(
                f"{self.error or 'GPU sensor stream is not running'}; "
                f"stderr={self.stderr_tail.strip()}"
            )

    def _wait_initial(self) -> None:
        deadline = monotonic_seconds() + STARTUP_SECONDS
        while monotonic_seconds() < deadline:
            with self.lock:
                self._alive()
                if self.pending is not None:
                    return
            sleep_seconds(0.01)
        raise ValueError("GPU stream startup timeout after 5 seconds; inference refused")

    def sample(self) -> ResourceSample:
        deadline = monotonic_seconds() + FRESH_SECONDS
        while True:
            with self.lock:
                self._alive()
                if self.latest_at is not None:
                    age = monotonic_seconds() - self.latest_at
                    if not 0 <= age <= FRESH_SECONDS:
                        self.error = "GPU sensor stream sample stale"
                        raise ValueError(self.error)
                if self.pending is not None:
                    sample, self.pending = self.pending, None
                    return sample
                if monotonic_seconds() >= deadline:
                    self.error = "GPU sensor stream response timeout after 0.5 seconds"
                    raise ValueError(self.error)
            sleep_seconds(0.005)

    def close(self) -> None:
        with self.lock:
            self.closing = True
        process = self.process
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            for thread in (self.reader, self.stderr_reader):
                if thread is not None:
                    thread.join(timeout=1)
                    if thread.is_alive():
                        raise ValueError("GPU sensor reader cleanup failed")
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()

        if self.journal is not None:
            self.journal.close()

    def __exit__(self, *_: object) -> None:
        self.close()
