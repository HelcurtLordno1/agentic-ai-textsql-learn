from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.migrate_schema_spider_power_stop import (
    audited_guard_revision,
    current_clock_mhz,
    migration_is_current,
)


def test_clock_probe_refuses_clock_above_new_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "705\n")
    with pytest.raises(SystemExit, match="exceeds 700 MHz"):
        current_clock_mhz()
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "700\n")
    assert current_clock_mhz() == 700


def test_schema_guard_revision_accepts_only_spider_clock_change(tmp_path: Path) -> None:
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
        "    maximum_gpu_power_w=70,\n    maximum_gpu_graphics_clock_mhz=901,\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "old"], cwd=tmp_path, check=True)
    previous = git("rev-parse", "HEAD")
    hardware.write_text(hardware.read_text().replace("=901,", "=701,"), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "guard"], cwd=tmp_path, check=True)
    current = git("rev-parse", "HEAD")
    assert audited_guard_revision(tmp_path, previous, current) == [
        "src/agentic_text2sql/hardware.py"
    ]
    (tmp_path / "runtime.py").write_text("changed", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "runtime"], cwd=tmp_path, check=True)
    with pytest.raises(SystemExit, match="inference or other files changed"):
        audited_guard_revision(tmp_path, previous, git("rev-parse", "HEAD"))


def test_migration_identity_requires_same_stop_hash_and_commit(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "tracked").write_text("version", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "version"], cwd=tmp_path, check=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    stop = tmp_path / "stop.json"
    stop.write_text("incident", encoding="utf-8")
    import hashlib

    digest = hashlib.sha256(stop.read_bytes()).hexdigest()
    provenance = tmp_path / "provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "git_commit": commit,
                "guard_revision_history": [
                    {"kind": "schema_spider_power_stop_700mhz", "prior_stop_sha256": digest}
                ],
            }
        ),
        encoding="utf-8",
    )
    assert migration_is_current(provenance, tmp_path, stop)
    stop.write_text("different incident", encoding="utf-8")
    assert not migration_is_current(provenance, tmp_path, stop)
