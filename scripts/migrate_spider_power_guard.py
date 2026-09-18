"""Audit a lower-clock Spider guard revision after a power incident."""

from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
from pathlib import Path
from typing import Any

from agentic_text2sql.hardware import (
    PROFILES,
    ProfileName,
    ResourceLimits,
    ResourceSample,
    unsafe_reason,
)
from agentic_text2sql_eval.inference_runner import SmokePrediction
from agentic_text2sql_eval.spider_release import load_release_cases, sha256_file
from scripts.migrate_spider_clock_guard import git_output
from scripts.run_benchmark import checkpoint_json

_SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")
_POWER_REASON = re.compile(r"^GPU power (\d+(?:\.\d+)?) W$")
_HARDWARE_PATH = "src/agentic_text2sql/hardware.py"
_ALLOWED_PATHS = {
    _HARDWARE_PATH,
    "scripts/launch_r2_spider_tmux.py",
    "scripts/migrate_spider_power_guard.py",
    "tests/unit/test_spider_guarded_resume.py",
    "tests/unit/test_spider_clock_guard_migration.py",
    "tests/unit/test_spider_deadline_guard_migration.py",
    "tests/unit/test_spider_power_guard_migration.py",
    "docs/runbook.md",
    "realistic_project_creation_codex.md",
}


def verified_clock_state() -> int:
    """Check the live clock; Administrator cap confirmation remains an explicit prerequisite."""
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "-i",
                "0",
                "--query-gpu=clocks.current.graphics",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        )
        current = int(output.strip())
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise SystemExit(f"CLOCK_STATE_UNVERIFIED: {type(exc).__name__}") from exc
    if not 0 < current <= 900:
        raise SystemExit(
            f"CLOCK_STATE_UNVERIFIED: current {current} MHz exceeds 900 MHz; "
            "require Administrator nvidia-smi -i 0 -lgc 300,900"
        )
    return current


def reviewed_power_stop(path: Path, limits: ResourceLimits) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"POWER_STOP_RECORD_REQUIRED: {path}")
    record = json.loads(path.read_text(encoding="utf-8"))
    match = _POWER_REASON.fullmatch(str(record.get("reason", "")))
    if record.get("stop_kind") != "resource_threshold" or match is None:
        raise SystemExit("POWER_STOP_REVIEW_REFUSED: incident was not power-only")
    observed = ResourceSample(**record["observed_peak"])
    if observed.gpu_power_w < 70 or float(match.group(1)) < 70:
        raise SystemExit("POWER_STOP_REVIEW_REFUSED: inconsistent power peak")
    # This historical sample predates the lower clock cap; review all other limits.
    other_limits = limits.model_copy(
        update={"maximum_gpu_power_w": 1000, "maximum_gpu_graphics_clock_mhz": 10000}
    )
    if reason := unsafe_reason(observed, other_limits):
        raise SystemExit(f"POWER_STOP_REVIEW_REFUSED: another threshold breached: {reason}")
    return record


def power_migration_is_current(provenance_path: Path, root: Path, stop_path: Path) -> bool:
    if not provenance_path.is_file() or not stop_path.is_file():
        return False
    payload = json.loads(provenance_path.read_text(encoding="utf-8"))
    history = payload.get("guard_revision_history", [])
    if not isinstance(history, list):
        return False
    try:
        commit = git_output(root, "rev-parse", "HEAD")
    except (OSError, subprocess.SubprocessError):
        return False
    return payload.get("git_commit") == commit and any(
        isinstance(item, dict)
        and item.get("kind") == "power_incident_clock_cap_revision"
        and item.get("prior_stop_sha256") == sha256_file(stop_path)
        for item in history
    )


def audited_power_revision(root: Path, previous_commit: str, current_commit: str) -> list[str]:
    if not re.fullmatch(r"[0-9a-f]{40}", previous_commit):
        raise SystemExit("SPIDER_POWER_MIGRATION_REFUSED: invalid previous commit")
    if (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", previous_commit, current_commit],
            cwd=root,
            check=False,
        ).returncode
        != 0
    ):
        raise SystemExit("SPIDER_POWER_MIGRATION_REFUSED: previous commit is not an ancestor")
    changed = git_output(root, "diff", "--name-only", previous_commit, current_commit).splitlines()
    if _HARDWARE_PATH not in changed or set(changed) - _ALLOWED_PATHS:
        raise SystemExit("SPIDER_POWER_MIGRATION_REFUSED: inference or non-guard files changed")
    old_hardware = git_output(root, "show", f"{previous_commit}:{_HARDWARE_PATH}")
    current_hardware = (root / _HARDWARE_PATH).read_text(encoding="utf-8").strip()
    marker = "    ProfileName.SPIDER_PAPER2: HardwareProfile("
    if old_hardware.count(marker) != 1 or current_hardware.count(marker) != 1:
        raise SystemExit("SPIDER_POWER_MIGRATION_REFUSED: Spider profile missing")
    prefix, spider = old_hardware.split(marker, maxsplit=1)
    old_clock = "maximum_gpu_graphics_clock_mhz=1201,"
    if spider.count(old_clock) != 1 or current_hardware != (
        prefix + marker + spider.replace(old_clock, "maximum_gpu_graphics_clock_mhz=901,", 1)
    ):
        raise SystemExit(
            "SPIDER_POWER_MIGRATION_REFUSED: hardware changed beyond Spider clock ceiling"
        )
    if git_output(root, "status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("SPIDER_POWER_MIGRATION_REFUSED: tracked worktree is dirty")
    return changed


def migrate(
    root: Path, evaluation_id: str, *, stop_session: str, hard_clock_cap_confirmed: bool
) -> dict[str, Any]:
    if _SAFE_NAME.fullmatch(evaluation_id) is None or _SAFE_NAME.fullmatch(stop_session) is None:
        raise SystemExit("invalid evaluation ID or stop session")
    with socket.socket() as connection:
        connection.settimeout(0.25)
        if connection.connect_ex(("127.0.0.1", 11434)) == 0:
            raise SystemExit("SPIDER_POWER_MIGRATION_REFUSED: Ollama server still active")
    if not hard_clock_cap_confirmed:
        raise SystemExit(
            "HARD_CLOCK_CAP_CONFIRMATION_REQUIRED: run Administrator "
            "nvidia-smi -i 0 -lgc 300,900 before migration"
        )
    current_clock = verified_clock_state()
    profile = PROFILES[ProfileName.SPIDER_PAPER2]
    if (
        profile.limits.maximum_gpu_power_w != 70
        or profile.limits.maximum_gpu_graphics_clock_mhz != 901
    ):
        raise SystemExit("SPIDER_POWER_MIGRATION_REFUSED: unexpected Spider guard limits")
    predictions_path = root / "evals/predictions" / f"{evaluation_id}.jsonl"
    provenance_path = predictions_path.with_suffix(".provenance.json")
    stop_path = root / "evals/reports" / f"{evaluation_id}.{stop_session}.resource-stop.json"
    incident = reviewed_power_stop(stop_path, profile.limits)
    if not predictions_path.is_file() or not provenance_path.is_file():
        raise SystemExit("SPIDER_POWER_MIGRATION_REFUSED: checkpoint or provenance missing")
    if power_migration_is_current(provenance_path, root, stop_path):
        raise SystemExit("SPIDER_POWER_MIGRATION_ALREADY_APPLIED")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    previous_commit = str(provenance.get("git_commit", ""))
    current_commit = git_output(root, "rev-parse", "HEAD")
    changed = audited_power_revision(root, previous_commit, current_commit)
    if provenance.get("experiment_id") != evaluation_id:
        raise SystemExit("SPIDER_POWER_MIGRATION_REFUSED: evaluation ID mismatch")
    manifest_path = root / "evals/configs/spider-laptop-200.json"
    if provenance.get("manifest_sha256") != sha256_file(manifest_path):
        raise SystemExit("SPIDER_POWER_MIGRATION_REFUSED: manifest changed")
    manifest, cases = load_release_cases(root / "data/raw/spider/spider_data", manifest_path)
    if manifest.case_count != 200:
        raise SystemExit("SPIDER_POWER_MIGRATION_REFUSED: manifest count changed")
    predictions = [
        SmokePrediction.model_validate_json(line)
        for line in predictions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(predictions) != incident.get("checkpoint") or [item.case_id for item in predictions] != [
        case.id for case in cases[: len(predictions)]
    ]:
        raise SystemExit("SPIDER_POWER_MIGRATION_REFUSED: checkpoint prefix mismatch")
    if provenance.get("index_pointer_sha256") != {
        db_id: sha256_file(root / "data/indexes/p3_1_semantic" / db_id / "active.json")
        for db_id in sorted(manifest.database_sha256)
    }:
        raise SystemExit("SPIDER_POWER_MIGRATION_REFUSED: active index pointer changed")
    configuration = provenance.get("run_config")
    if not isinstance(configuration, dict) or any(
        configuration.get(key) != value
        for key, value in {
            "resource_profile": profile.name.value,
            "num_gpu": profile.ollama_num_gpu,
            "planning_mode": "hybrid",
            "candidate_mode": "legacy",
            "correction_enabled": True,
            "retrieval_mode": profile.retrieval_mode,
            "max_output_tokens": profile.max_output_tokens,
            "request_timeout_seconds": profile.request_timeout_seconds,
            "run_deadline_seconds": profile.run_deadline_seconds,
        }.items()
    ):
        raise SystemExit("SPIDER_POWER_MIGRATION_REFUSED: inference configuration changed")
    history = provenance.get("guard_revision_history")
    if not isinstance(history, list) or [item.get("kind") for item in history] != [
        "clock_guard_only_revision",
        "deadline_guard_only_revision",
    ]:
        raise SystemExit("SPIDER_POWER_MIGRATION_REFUSED: expected prior guard migrations")
    audit: dict[str, Any] = {
        "kind": "power_incident_clock_cap_revision",
        "from_git_commit": previous_commit,
        "to_git_commit": current_commit,
        "start_case_index": len(predictions),
        "old_maximum_graphics_clock_mhz": 1200,
        "new_maximum_graphics_clock_mhz": 900,
        "gpu_power_stop_w": 70,
        "administrator_hard_clock_cap_confirmed": True,
        "observed_clock_mhz_at_migration": current_clock,
        "prior_stop_sha256": sha256_file(stop_path),
        "predictions_sha256_at_migration": sha256_file(predictions_path),
        "changed_paths": changed,
        "inference_implementation_unchanged": True,
    }
    history.append(audit)
    provenance["git_commit"] = current_commit
    audit_path = root / "evals/reports" / f"{evaluation_id}.power-guard-migration.json"
    checkpoint_json(audit_path, audit)
    checkpoint_json(provenance_path, provenance)
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation-id", required=True)
    parser.add_argument("--stop-session", required=True)
    parser.add_argument("--hard-clock-cap-confirmed", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            migrate(
                Path(__file__).resolve().parents[1],
                args.evaluation_id,
                stop_session=args.stop_session,
                hard_clock_cap_confirmed=args.hard_clock_cap_confirmed,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
