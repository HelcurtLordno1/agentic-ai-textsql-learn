"""Audit the schema-ablation Spider checkpoint after the 900 MHz power stop.

The migration changes only the Spider clock guard. Saved predictions and the
original stop record remain intact; the next case must pass a guarded pilot.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
from pathlib import Path
from typing import Any

from agentic_text2sql.hardware import PROFILES, ProfileName
from agentic_text2sql_eval.inference_runner import SmokePrediction
from agentic_text2sql_eval.spider_release import load_release_cases, sha256_file
from scripts.migrate_spider_clock_guard import git_output
from scripts.migrate_spider_power_guard import reviewed_power_stop
from scripts.run_benchmark import checkpoint_json

EVALUATION_ID = "spider-schema-legacy-200-v1"
HARDWARE_PATH = "src/agentic_text2sql/hardware.py"
ALLOWED_PATHS = {
    HARDWARE_PATH,
    "scripts/launch_r2_spider_tmux.py",
    "scripts/migrate_schema_spider_power_stop.py",
    "tests/unit/test_spider_guarded_resume.py",
    "tests/unit/test_schema_spider_power_stop.py",
    "docs/runbook.md",
}


def current_clock_mhz() -> int:
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
        clock = int(output.strip())
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise SystemExit(f"CLOCK_STATE_UNVERIFIED: {type(exc).__name__}") from exc
    if not 0 < clock <= 700:
        raise SystemExit(f"CLOCK_STATE_UNVERIFIED: current {clock} MHz exceeds 700 MHz")
    return clock


def migration_is_current(provenance_path: Path, root: Path, stop_path: Path) -> bool:
    if not provenance_path.is_file() or not stop_path.is_file():
        return False
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    history = provenance.get("guard_revision_history", [])
    return (
        provenance.get("git_commit") == git_output(root, "rev-parse", "HEAD")
        and isinstance(history, list)
        and any(
            isinstance(item, dict)
            and item.get("kind") == "schema_spider_power_stop_700mhz"
            and item.get("prior_stop_sha256") == sha256_file(stop_path)
            for item in history
        )
    )


def audited_guard_revision(root: Path, previous_commit: str, current_commit: str) -> list[str]:
    if not re.fullmatch(r"[0-9a-f]{40}", previous_commit):
        raise SystemExit("SCHEMA_POWER_MIGRATION_REFUSED: invalid previous commit")
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", previous_commit, current_commit],
        cwd=root,
        check=False,
    ).returncode:
        raise SystemExit("SCHEMA_POWER_MIGRATION_REFUSED: previous commit is not an ancestor")
    changed = git_output(root, "diff", "--name-only", previous_commit, current_commit).splitlines()
    if HARDWARE_PATH not in changed or set(changed) - ALLOWED_PATHS:
        raise SystemExit("SCHEMA_POWER_MIGRATION_REFUSED: inference or other files changed")
    before = git_output(root, "show", f"{previous_commit}:{HARDWARE_PATH}")
    after = (root / HARDWARE_PATH).read_text(encoding="utf-8").strip()
    marker = "    ProfileName.SPIDER_PAPER2: HardwareProfile("
    if before.count(marker) != 1 or after.count(marker) != 1:
        raise SystemExit("SCHEMA_POWER_MIGRATION_REFUSED: Spider profile missing")
    prefix, spider = before.split(marker, 1)
    old = "maximum_gpu_graphics_clock_mhz=901,"
    if spider.count(old) != 1 or after != prefix + marker + spider.replace(
        old, "maximum_gpu_graphics_clock_mhz=701,", 1
    ):
        raise SystemExit("SCHEMA_POWER_MIGRATION_REFUSED: hardware change is not guard-only")
    if git_output(root, "status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("SCHEMA_POWER_MIGRATION_REFUSED: tracked worktree is dirty")
    return changed


def migrate(root: Path, *, hard_clock_cap_confirmed: bool) -> dict[str, Any]:
    if not hard_clock_cap_confirmed:
        raise SystemExit("HARD_CLOCK_CAP_CONFIRMATION_REQUIRED: Administrator -lgc 300,700")
    with socket.socket() as connection:
        connection.settimeout(0.25)
        if connection.connect_ex(("127.0.0.1", 11434)) == 0:
            raise SystemExit("SCHEMA_POWER_MIGRATION_REFUSED: Ollama server is active")
    observed_clock = current_clock_mhz()
    profile = PROFILES[ProfileName.SPIDER_PAPER2]
    if (
        profile.limits.maximum_gpu_power_w != 70
        or profile.limits.maximum_gpu_graphics_clock_mhz != 701
    ):
        raise SystemExit("SCHEMA_POWER_MIGRATION_REFUSED: unexpected Spider limits")
    predictions_path = root / "evals/predictions" / f"{EVALUATION_ID}.jsonl"
    provenance_path = predictions_path.with_suffix(".provenance.json")
    stop_path = root / "evals/reports" / f"{EVALUATION_ID}.resource-stop.json"
    incident = reviewed_power_stop(stop_path, profile.limits)
    if not predictions_path.is_file() or not provenance_path.is_file():
        raise SystemExit("SCHEMA_POWER_MIGRATION_REFUSED: checkpoint or provenance missing")
    if migration_is_current(provenance_path, root, stop_path):
        raise SystemExit("SCHEMA_POWER_MIGRATION_ALREADY_APPLIED")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    previous_commit = str(provenance.get("git_commit", ""))
    current_commit = git_output(root, "rev-parse", "HEAD")
    changed = audited_guard_revision(root, previous_commit, current_commit)
    if (
        provenance.get("experiment_id") != EVALUATION_ID
        or provenance.get("run_config", {}).get("schema_context_mode") != "legacy"
    ):
        raise SystemExit("SCHEMA_POWER_MIGRATION_REFUSED: experiment or mode changed")
    manifest_path = root / "evals/configs/spider-laptop-200.json"
    if provenance.get("manifest_sha256") != sha256_file(manifest_path):
        raise SystemExit("SCHEMA_POWER_MIGRATION_REFUSED: manifest changed")
    manifest, cases = load_release_cases(root / "data/raw/spider/spider_data", manifest_path)
    predictions = [
        SmokePrediction.model_validate_json(line)
        for line in predictions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if (
        manifest.case_count != 200
        or len(predictions) != incident.get("checkpoint")
        or [item.case_id for item in predictions] != [case.id for case in cases[: len(predictions)]]
    ):
        raise SystemExit("SCHEMA_POWER_MIGRATION_REFUSED: checkpoint prefix changed")
    index_root = root / "data/indexes/p3_1_semantic"
    if provenance.get("index_pointer_sha256") != {
        db_id: sha256_file(index_root / db_id / "active.json")
        for db_id in sorted(manifest.database_sha256)
    }:
        raise SystemExit("SCHEMA_POWER_MIGRATION_REFUSED: index pointers changed")
    if provenance.get("guard_revision_history") not in (None, []):
        raise SystemExit("SCHEMA_POWER_MIGRATION_REFUSED: unexpected migration history")
    audit: dict[str, Any] = {
        "kind": "schema_spider_power_stop_700mhz",
        "from_git_commit": previous_commit,
        "to_git_commit": current_commit,
        "start_case_index": len(predictions),
        "old_maximum_graphics_clock_mhz": 900,
        "new_maximum_graphics_clock_mhz": 700,
        "gpu_power_stop_w": 70,
        "administrator_hard_clock_cap_confirmed": True,
        "observed_clock_mhz_at_migration": observed_clock,
        "pilot_required": True,
        "prior_stop_sha256": sha256_file(stop_path),
        "predictions_sha256_at_migration": sha256_file(predictions_path),
        "changed_paths": changed,
        "inference_implementation_unchanged": True,
    }
    provenance["source_git_commit"] = previous_commit
    provenance["git_commit"] = current_commit
    provenance["guard_revision_history"] = [audit]
    checkpoint_json(root / "evals/reports" / f"{EVALUATION_ID}.700mhz-migration.json", audit)
    checkpoint_json(provenance_path, provenance)
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hard-clock-cap-confirmed", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            migrate(
                Path(__file__).resolve().parents[1],
                hard_clock_cap_confirmed=args.hard_clock_cap_confirmed,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
