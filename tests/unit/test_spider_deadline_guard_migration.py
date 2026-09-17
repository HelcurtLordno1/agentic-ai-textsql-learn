from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentic_text2sql.hardware import PROFILES, ProfileName
from scripts.migrate_spider_deadline_guard import audited_deadline_revision, reviewed_deadline_stop


def test_reviewed_deadline_requires_exact_timeout_and_safe_resources(tmp_path: Path) -> None:
    path = tmp_path / "stop.json"
    incident = {
        "stop_kind": "batch_deadline",
        "reason": "child deadline 360s",
        "checkpoint": 170,
        "observed_peak": {
            "available_ram_gib": 22.39,
            "swap_used_gib": 0,
            "gpu_memory_mib": 1790,
            "gpu_temperature_c": 58,
            "gpu_power_w": 66.34,
            "gpu_utilization_pct": 97,
            "gpu_graphics_clock_mhz": 1200,
        },
    }
    limits = PROFILES[ProfileName.SPIDER_PAPER2].limits
    path.write_text(json.dumps(incident), encoding="utf-8")
    assert reviewed_deadline_stop(path, limits) == incident
    incident["reason"] = "GPU power 70.0 W"
    path.write_text(json.dumps(incident), encoding="utf-8")
    with pytest.raises(SystemExit, match="not the 360s batch deadline"):
        reviewed_deadline_stop(path, limits)
    incident["reason"] = "child deadline 360s"
    incident["observed_peak"]["gpu_power_w"] = limits.maximum_gpu_power_w  # type: ignore[index]
    path.write_text(json.dumps(incident), encoding="utf-8")
    with pytest.raises(SystemExit, match="resource threshold breached"):
        reviewed_deadline_stop(path, limits)


def test_deadline_revision_accepts_guard_only_and_rejects_runtime_edit(tmp_path: Path) -> None:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    launcher = tmp_path / "scripts/launch_r2_spider_tmux.py"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("batch_timeout_seconds=360\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "old"], cwd=tmp_path, check=True)
    previous = git("rev-parse", "HEAD")
    launcher.write_text("batch_timeout_seconds=900\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "guard"], cwd=tmp_path, check=True)
    current = git("rev-parse", "HEAD")
    assert audited_deadline_revision(tmp_path, previous, current) == [
        "scripts/launch_r2_spider_tmux.py"
    ]
    runtime = tmp_path / "src/agentic_text2sql/runtime.py"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("changed", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "runtime"], cwd=tmp_path, check=True)
    with pytest.raises(SystemExit, match="inference or non-guard files changed"):
        audited_deadline_revision(tmp_path, previous, git("rev-parse", "HEAD"))
