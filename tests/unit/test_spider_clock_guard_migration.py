from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentic_text2sql.hardware import PROFILES, ProfileName
from scripts.migrate_spider_clock_guard import (
    audited_guard_only_revision,
    reviewed_clock_stop,
)


def test_clock_stop_requires_clock_only_and_safe_other_peaks(tmp_path: Path) -> None:
    limits = PROFILES[ProfileName.SPIDER_PAPER2].limits
    record = {
        "stop_kind": "resource_threshold",
        "reason": "GPU graphics clock 900 MHz",
        "observed_peak": {
            "available_ram_gib": 22.1,
            "swap_used_gib": 0,
            "gpu_memory_mib": 2347,
            "gpu_temperature_c": 56,
            "gpu_power_w": 53.42,
            "gpu_utilization_pct": 98,
            "gpu_graphics_clock_mhz": 900,
        },
    }
    path = tmp_path / "stop.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert reviewed_clock_stop(path, limits) == record
    record["reason"] = "GPU power 72.0 W"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(SystemExit, match="not clock-only"):
        reviewed_clock_stop(path, limits)
    record["reason"] = "GPU graphics clock 900 MHz"
    record["observed_peak"]["gpu_power_w"] = limits.maximum_gpu_power_w  # type: ignore[index]
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(SystemExit, match="another threshold breached"):
        reviewed_clock_stop(path, limits)


def test_revision_audit_rejects_runtime_change(tmp_path: Path) -> None:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    hardware = tmp_path / "src/agentic_text2sql/hardware.py"
    hardware.parent.mkdir(parents=True)
    hardware.write_text("maximum_gpu_graphics_clock_mhz=601,\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "old"], cwd=tmp_path, check=True)
    previous = git("rev-parse", "HEAD")
    hardware.write_text("maximum_gpu_graphics_clock_mhz=1201,\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "guard only"], cwd=tmp_path, check=True)
    current = git("rev-parse", "HEAD")
    assert audited_guard_only_revision(tmp_path, previous, current) == [
        "src/agentic_text2sql/hardware.py"
    ]
    runtime = tmp_path / "src/agentic_text2sql/runtime.py"
    runtime.write_text("changed inference", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "runtime changed"], cwd=tmp_path, check=True)
    with pytest.raises(SystemExit, match="non-guard files changed"):
        audited_guard_only_revision(tmp_path, previous, git("rev-parse", "HEAD"))
