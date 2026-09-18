from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentic_text2sql.hardware import PROFILES, ProfileName
from scripts.migrate_spider_power_guard import (
    audited_power_revision,
    reviewed_power_stop,
    verified_clock_state,
)


def test_clock_state_refuses_over_900_mhz(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "1200\n")
    with pytest.raises(SystemExit, match="CLOCK_STATE_UNVERIFIED"):
        verified_clock_state()
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "900\n")
    assert verified_clock_state() == 900


def test_power_stop_requires_power_only_and_safe_other_peaks(tmp_path: Path) -> None:
    incident = {
        "stop_kind": "resource_threshold",
        "reason": "GPU power 87.8 W",
        "checkpoint": 174,
        "observed_peak": {
            "available_ram_gib": 22.43,
            "swap_used_gib": 0,
            "gpu_memory_mib": 1789,
            "gpu_temperature_c": 57,
            "gpu_power_w": 87.82,
            "gpu_utilization_pct": 98,
            "gpu_graphics_clock_mhz": 1200,
        },
    }
    limits = PROFILES[ProfileName.SPIDER_PAPER2].limits
    path = tmp_path / "stop.json"
    path.write_text(json.dumps(incident), encoding="utf-8")
    assert reviewed_power_stop(path, limits) == incident
    incident["reason"] = "GPU temperature 70 C"
    path.write_text(json.dumps(incident), encoding="utf-8")
    with pytest.raises(SystemExit, match="not power-only"):
        reviewed_power_stop(path, limits)
    incident["reason"] = "GPU power 87.8 W"
    incident["observed_peak"]["gpu_temperature_c"] = 65  # type: ignore[index]
    path.write_text(json.dumps(incident), encoding="utf-8")
    with pytest.raises(SystemExit, match="another threshold breached"):
        reviewed_power_stop(path, limits)


def test_power_revision_rejects_any_other_hardware_or_runtime_change(tmp_path: Path) -> None:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    hardware = tmp_path / "src/agentic_text2sql/hardware.py"
    hardware.parent.mkdir(parents=True)
    hardware.write_text(
        "header\n    ProfileName.SPIDER_PAPER2: HardwareProfile(\n"
        "    maximum_gpu_power_w=70,\n    maximum_gpu_graphics_clock_mhz=1201,\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "old"], cwd=tmp_path, check=True)
    previous = git("rev-parse", "HEAD")
    hardware.write_text(
        hardware.read_text(encoding="utf-8").replace("=1201,", "=901,"), encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "power guard"], cwd=tmp_path, check=True)
    assert audited_power_revision(tmp_path, previous, git("rev-parse", "HEAD")) == [
        "src/agentic_text2sql/hardware.py"
    ]
    runtime = tmp_path / "src/agentic_text2sql/runtime.py"
    runtime.write_text("inference changed", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "runtime"], cwd=tmp_path, check=True)
    with pytest.raises(SystemExit, match="inference or non-guard files changed"):
        audited_power_revision(tmp_path, previous, git("rev-parse", "HEAD"))
