"""Durable lifecycle state for operator pause/resume, separate from resource latches."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentic_text2sql_eval.runtime_checkpoint import atomic_json


class SuiteState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = "suite-state-v1"
    phase: Literal["READY", "RUNNING", "COOLING", "PAUSED", "COMPLETE", "FAILED", "RESOURCE_STOP"]
    completed: int = Field(ge=0)
    total: int = Field(ge=1)
    identity: str
    boot_id: str
    pid: int = Field(gt=0)
    child_pid: int | None = Field(default=None, gt=0)
    cooldown_until: float = 0
    recovery_required: bool = False
    cleanup_pending: bool = False
    reason: str | None = None
    updated_at: float = Field(default_factory=time.time)


def boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()


def process_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def process_group_alive(pid: int | None) -> bool:
    """The guarded worker owns a process group; its leader may exit before a child."""
    if pid is None:
        return False
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def prediction_prefix(path: Path, expected_ids: list[str]) -> int:
    if not path.exists():
        return 0
    ids = [
        json.loads(line)["case_id"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if ids != expected_ids[: len(ids)] or len(ids) > len(expected_ids):
        raise ValueError("Checkpoint is not a complete, duplicate-free manifest prefix")
    return len(ids)


def write_state(path: Path, state: SuiteState) -> None:
    state.updated_at = time.time()
    atomic_json(path, state.model_dump(mode="json"))


def require_complete_report(path: Path, expected_ids: list[str]) -> None:
    report = json.loads(path.read_text(encoding="utf-8"))
    details = report.get("details")
    if not isinstance(details, list) or [item.get("id") for item in details] != expected_ids:
        raise ValueError("Final report is missing, partial, or belongs to another manifest")
    if report.get("case_count") != len(expected_ids):
        raise ValueError("Final report case count does not match the complete checkpoint")
