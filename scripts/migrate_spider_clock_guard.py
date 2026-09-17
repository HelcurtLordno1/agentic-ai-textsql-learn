"""Audit a clock-only guard revision before resuming pinned Spider predictions.

This does not infer, score, or change any saved prediction. It preserves the original
incident and records the exact checkpoint at which the guard revision changed.
"""

from __future__ import annotations

import argparse
import json
import re
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
from scripts.run_benchmark import checkpoint_json

_SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")
_CLOCK_STOP = re.compile(r"^GPU graphics clock (\d+) MHz$")
_HARDWARE_PATH = "src/agentic_text2sql/hardware.py"
_ALLOWED_PATHS = {
    _HARDWARE_PATH,
    "scripts/launch_r2_spider_tmux.py",
    "scripts/migrate_spider_clock_guard.py",
    "tests/unit/test_spider_guarded_resume.py",
    "tests/unit/test_spider_clock_guard_migration.py",
    "docs/runbook.md",
    "realistic_project_creation_codex.md",
}


def git_output(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True, timeout=10).strip()


def reviewed_clock_stop(path: Path, limits: ResourceLimits) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"CLOCK_STOP_RECORD_REQUIRED: {path}")
    record = json.loads(path.read_text(encoding="utf-8"))
    match = _CLOCK_STOP.fullmatch(str(record.get("reason", "")))
    if record.get("stop_kind") != "resource_threshold" or match is None:
        raise SystemExit("CLOCK_STOP_REVIEW_REFUSED: incident was not clock-only")
    observed = ResourceSample(**record["observed_peak"])
    if observed.gpu_graphics_clock_mhz > 1200 or int(match.group(1)) > 1200:
        raise SystemExit("CLOCK_STOP_REVIEW_REFUSED: observed clock exceeded new hard cap")
    nonclock_limits = limits.model_copy(update={"maximum_gpu_graphics_clock_mhz": 10000})
    if reason := unsafe_reason(observed, nonclock_limits):
        raise SystemExit(f"CLOCK_STOP_REVIEW_REFUSED: another threshold breached: {reason}")
    return record


def migration_is_current(provenance_path: Path, root: Path, prior_stop: Path) -> bool:
    if not provenance_path.is_file():
        return False
    payload = json.loads(provenance_path.read_text(encoding="utf-8"))
    history = payload.get("guard_revision_history", [])
    if not isinstance(history, list) or not history:
        return False
    try:
        commit = git_output(root, "rev-parse", "HEAD")
    except (OSError, subprocess.SubprocessError):
        return False
    return (
        payload.get("git_commit") == commit
        and history[-1].get("to_git_commit") == commit
        and history[-1].get("prior_stop_sha256") == sha256_file(prior_stop)
    )


def audited_guard_only_revision(root: Path, previous_commit: str, current_commit: str) -> list[str]:
    if not re.fullmatch(r"[0-9a-f]{40}", previous_commit):
        raise SystemExit("SPIDER_MIGRATION_REFUSED: invalid previous commit")
    if (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", previous_commit, current_commit],
            cwd=root,
            check=False,
        ).returncode
        != 0
    ):
        raise SystemExit("SPIDER_MIGRATION_REFUSED: previous commit is not an ancestor")
    changed = git_output(root, "diff", "--name-only", previous_commit, current_commit).splitlines()
    if _HARDWARE_PATH not in changed or set(changed) - _ALLOWED_PATHS:
        raise SystemExit("SPIDER_MIGRATION_REFUSED: non-guard files changed")
    old_hardware = git_output(root, "show", f"{previous_commit}:{_HARDWARE_PATH}")
    current_hardware = (root / _HARDWARE_PATH).read_text(encoding="utf-8").strip()
    old_clock = "maximum_gpu_graphics_clock_mhz=601,"
    if old_hardware.count(old_clock) != 1 or current_hardware != old_hardware.replace(
        old_clock, "maximum_gpu_graphics_clock_mhz=1201,"
    ):
        raise SystemExit("SPIDER_MIGRATION_REFUSED: hardware changed beyond clock ceiling")
    if git_output(root, "status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("SPIDER_MIGRATION_REFUSED: tracked worktree is dirty")
    return changed


def migrate(root: Path, evaluation_id: str) -> dict[str, Any]:
    if _SAFE_NAME.fullmatch(evaluation_id) is None:
        raise SystemExit("invalid evaluation ID")
    profile = PROFILES[ProfileName.SPIDER_PAPER2]
    if profile.limits.maximum_gpu_graphics_clock_mhz != 1201:
        raise SystemExit("SPIDER_MIGRATION_REFUSED: unexpected new clock ceiling")
    predictions_path = root / "evals/predictions" / f"{evaluation_id}.jsonl"
    provenance_path = predictions_path.with_suffix(".provenance.json")
    stop_path = root / "evals/reports" / f"{evaluation_id}.resource-stop.json"
    reviewed_clock_stop(stop_path, profile.limits)
    if not predictions_path.is_file() or not provenance_path.is_file():
        raise SystemExit("SPIDER_MIGRATION_REFUSED: checkpoint or provenance missing")
    if migration_is_current(provenance_path, root, stop_path):
        raise SystemExit("SPIDER_MIGRATION_ALREADY_APPLIED")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    previous_commit = str(provenance.get("git_commit", ""))
    current_commit = git_output(root, "rev-parse", "HEAD")
    changed = audited_guard_only_revision(root, previous_commit, current_commit)
    if provenance.get("experiment_id") != evaluation_id:
        raise SystemExit("SPIDER_MIGRATION_REFUSED: evaluation ID mismatch")
    configuration = provenance.get("run_config", {})
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
        raise SystemExit("SPIDER_MIGRATION_REFUSED: inference configuration changed")
    manifest_path = root / "evals/configs/spider-laptop-200.json"
    if provenance.get("manifest_sha256") != sha256_file(manifest_path):
        raise SystemExit("SPIDER_MIGRATION_REFUSED: manifest changed")
    manifest, cases = load_release_cases(root / "data/raw/spider/spider_data", manifest_path)
    if manifest.case_count != 200:
        raise SystemExit("SPIDER_MIGRATION_REFUSED: manifest count changed")
    existing = [
        SmokePrediction.model_validate_json(line)
        for line in predictions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not existing or [item.case_id for item in existing] != [
        case.id for case in cases[: len(existing)]
    ]:
        raise SystemExit("SPIDER_MIGRATION_REFUSED: prediction prefix invalid")
    index_hashes = provenance.get("index_pointer_sha256", {})
    if not isinstance(index_hashes, dict) or index_hashes != {
        db_id: sha256_file(root / "data/indexes/p3_1_semantic" / db_id / "active.json")
        for db_id in sorted(manifest.database_sha256)
    }:
        raise SystemExit("SPIDER_MIGRATION_REFUSED: active index pointer changed")
    audit: dict[str, Any] = {
        "kind": "clock_guard_only_revision",
        "from_git_commit": previous_commit,
        "to_git_commit": current_commit,
        "start_case_index": len(existing),
        "old_maximum_graphics_clock_mhz": 600,
        "new_maximum_graphics_clock_mhz": 1200,
        "prior_stop_sha256": sha256_file(stop_path),
        "predictions_sha256_at_migration": sha256_file(predictions_path),
        "changed_paths": changed,
        "inference_implementation_unchanged": True,
    }
    history = provenance.setdefault("guard_revision_history", [])
    if not isinstance(history, list) or history:
        raise SystemExit("SPIDER_MIGRATION_REFUSED: unexpected guard revision history")
    history.append(audit)
    provenance["source_git_commit"] = previous_commit
    provenance["git_commit"] = current_commit
    audit_path = root / "evals/reports" / f"{evaluation_id}.clock-guard-migration.json"
    checkpoint_json(audit_path, audit)
    checkpoint_json(provenance_path, provenance)
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation-id", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(migrate(root, args.evaluation_id), indent=2))


if __name__ == "__main__":
    main()
