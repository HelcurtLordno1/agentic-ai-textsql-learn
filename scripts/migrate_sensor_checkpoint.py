"""Explicit, audited continuation of a pre-spawn GPU-sensor timeout checkpoint.

This never clears a latch or launches inference. The old experiment is immutable;
only infrastructure source changes are admissible, with byte-identical predictions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path
from typing import Any

from agentic_text2sql.hardware import PROFILES
from agentic_text2sql.settings import Settings
from agentic_text2sql_eval.inference_runner import SmokePrediction
from agentic_text2sql_eval.runtime_checkpoint import atomic_json, file_sha256, runtime_identity
from agentic_text2sql_eval.suite_control import prediction_prefix, process_group_alive
from scripts.tmux_benchmarks import SequencePlan, SequenceState, directory, ids
from scripts.tmux_experiment import ROOT, ExperimentPlan, frozen_environment, plan_path

ALLOWED_CHANGES = frozenset(
    {
        "src/agentic_text2sql/gpu_monitor.py",
        "src/agentic_text2sql/hardware.py",
        "src/agentic_text2sql/resource_guard.py",
        "scripts/windows_gpu_stream.ps1",
        "scripts/windows_ollama_guard.ps1",
        "scripts/serve_ollama_guarded.py",
        "scripts/migrate_sensor_checkpoint.py",
    }
)
FIXED_FILES = (
    "pyproject.toml",
    "uv.lock",
    "configs/models.yaml",
    "datasets/olist/business_glossary.yaml",
)


def identity_file(name: str) -> bool:
    path = Path(name)
    return name in FIXED_FILES or (
        (path.parts[0] in {"src", "scripts"} or name.startswith("configs/prompts/"))
        and path.suffix in {".py", ".j2", ".ps1"}
    )


def source_digest(files: dict[str, str]) -> str:
    ordered = sorted(name for name in files if name not in FIXED_FILES)
    ordered.extend(FIXED_FILES)
    digest = hashlib.sha256()
    for name in ordered:
        digest.update(name.encode())
        digest.update(bytes.fromhex(files[name]))
    return digest.hexdigest()


def verify_changes(before: dict[str, str], after: dict[str, str]) -> dict[str, Any]:
    changed = {
        name: {"before": before.get(name), "after": after.get(name)}
        for name in sorted(before.keys() | after.keys())
        if before.get(name) != after.get(name)
    }
    if (
        not changed
        or set(changed) - ALLOWED_CHANGES
        or any(value["after"] is None for value in changed.values())
    ):
        raise ValueError("Migration requires only the approved monitor infrastructure changes")
    return changed


def migrate(parent: SequencePlan, name: str, snapshot: Path) -> dict[str, Any]:
    state = SequenceState.model_validate_json(
        (directory(parent) / "sequence-state.json").read_text()
    )
    if state.phase != "RESOURCE_STOP" or any(
        pid is not None for pid in (state.server_pid, state.worker_pid, state.proxy_pid)
    ):
        raise ValueError("Parent must be RESOURCE_STOP with all owners cleaned up")
    for child in parent.benchmarks:
        suite_state = Path(child.report).with_suffix(".suite-state.json")
        if suite_state.exists():
            old_state = json.loads(suite_state.read_text())
            if process_group_alive(old_state.get("child_pid")) or old_state.get("cleanup_pending"):
                raise ValueError("Parent suite child/cleanup still active")
        frozen_environment(child)
    incident_path = Path(parent.spider.report).with_suffix(".resource-stop.json")
    incident = json.loads(incident_path.read_text())
    if not (
        str(incident.get("reason", "")).startswith("monitor failure: TimeoutExpired:")
        and "nvidia-smi" in incident["reason"]
        and "0.5 seconds" in incident["reason"]
        and incident.get("samples") == 0
        and incident.get("observed_peak") is None
        and incident.get("cleanup_error") is None
        and incident.get("resource_stop") is True
    ):
        raise ValueError("Only the diagnosed pre-spawn sensor timeout is eligible")
    if (
        (directory(parent) / "server.resource-stop.json").exists()
        or (directory(parent) / "cleanup.resource-stop.json").exists()
        or Path(parent.olist.report).with_suffix(".resource-stop.json").exists()
    ):
        raise ValueError("Native/cleanup stop requires separate remediation")
    before: dict[str, str] = {}
    with tarfile.open(snapshot, "r:gz") as archive:
        for member in archive.getmembers():
            if member.isfile() and identity_file(member.name):
                handle = archive.extractfile(member)
                if handle is None:
                    raise ValueError("Missing snapshot member")
                before[member.name] = hashlib.sha256(handle.read()).hexdigest()
    after = {
        str(path.relative_to(ROOT)): file_sha256(path)
        for folder in ("src", "scripts", "configs/prompts")
        for path in (ROOT / folder).rglob("*")
        if path.is_file() and identity_file(str(path.relative_to(ROOT)))
    }
    after.update({name: file_sha256(ROOT / name) for name in FIXED_FILES})
    changed = verify_changes(before, after)
    old_digest, new_digest = source_digest(before), source_digest(after)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    preservation = {
        str(path): file_sha256(path) for path in directory(parent).rglob("*") if path.is_file()
    }
    writes: list[tuple[Path, bytes]] = []
    children: list[ExperimentPlan] = []
    lineage: dict[str, Any] = {
        "version": "sensor-continuation-v1",
        "parent": parent.name,
        "continuation": name,
        "reason": incident["reason"],
        "incident": str(incident_path),
        "incident_sha256": file_sha256(incident_path),
        "snapshot_sha256": file_sha256(snapshot),
        "parent_source_sha256": old_digest,
        "continuation_source_sha256": new_digest,
        "git_commit": head,
        "source_changes": changed,
        "prefixes": {},
        "claim": "Explicit infrastructure migration; inherited rows retain their original source",
    }
    for old in parent.benchmarks:
        if Path(old.report).exists():
            raise ValueError("Completed/scored suites must not be migrated")
        prefix = prediction_prefix(Path(old.predictions), ids(old))
        for line in Path(old.predictions).read_text().splitlines():
            if line.strip():
                SmokePrediction.model_validate_json(line)
        if prefix == 0 or prefix == len(ids(old)):
            raise ValueError("Migration requires a nonempty incomplete valid prefix")
        for path in ROOT.glob(f"evals/predictions/{parent.name}-{old.suite}.*"):
            preservation[str(path)] = file_sha256(path)
        for path in ROOT.glob(f"evals/reports/{parent.name}-{old.suite}.*"):
            if path.is_file():
                preservation[str(path)] = file_sha256(path)
        identity = json.loads(Path(old.predictions).with_suffix(".runtime.json").read_text())
        if identity["source_sha256"] != old_digest:
            raise ValueError("Original snapshot does not reproduce the parent source identity")
        settings = Settings(
            **{**old.settings_environment, **PROFILES[parent.profile].ollama_environment()}
        )
        manifest_flag = "--manifest" if old.suite == "spider" else "--cases"
        manifest = Path(old.wrapper_args[old.wrapper_args.index(manifest_flag) + 1])
        actual = runtime_identity(
            settings,
            identity["correction_enabled"],
            manifest,
            databases=[Path(path) for path in identity["database_sha256"]],
            selection=identity["selection"],
        )
        actual["resource_profile"] = PROFILES[parent.profile].model_dump_json()
        if actual != {**identity, "source_sha256": new_digest}:
            raise ValueError("Model/settings/profile/data/index drift; migration refused")
        predictions = ROOT / f"evals/predictions/{name}-{old.suite}.jsonl"
        report = ROOT / f"evals/reports/{name}-{old.suite}.json"
        wrapper = list(old.wrapper_args)
        wrapper[wrapper.index("--predictions") + 1] = str(predictions)
        wrapper[wrapper.index("--report") + 1] = str(report)
        new = old.model_copy(
            update={
                "name": f"{name}-{old.suite}",
                "predictions": str(predictions),
                "report": str(report),
                "wrapper_args": tuple(wrapper),
            }
        )
        children.append(new)
        writes.append((predictions, Path(old.predictions).read_bytes()))
        writes.append(
            (
                predictions.with_suffix(".runtime.json"),
                (json.dumps(actual, sort_keys=True, indent=2) + "\n").encode(),
            )
        )
        backend = Path(old.predictions).with_suffix(".backend.json")
        writes.append((predictions.with_suffix(".backend.json"), backend.read_bytes()))
        lineage["prefixes"][old.suite] = {
            "count": prefix,
            "predictions_sha256": file_sha256(Path(old.predictions)),
            "backend_sha256": file_sha256(backend),
            "source_sha256": old_digest,
        }
        provenance = Path(old.predictions).with_suffix(".provenance.json")
        if old.suite == "spider":
            payload = json.loads(provenance.read_text())
            if payload["git_commit"] != head:
                raise ValueError("Git HEAD changed from the parent")
            payload["run_config"]["source_sha256"] = new_digest
            payload["continuation_lineage"] = str(plan_path(name).parent / "continuation.json")
            writes.append(
                (
                    predictions.with_suffix(".provenance.json"),
                    (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode(),
                )
            )
    continuation = parent.model_copy(
        update={"name": name, "spider": children[0], "olist": children[1]}
    )
    # Validate name/plan before creating anything, not just model_copy's unchecked update.
    continuation = SequencePlan.model_validate(continuation.model_dump())
    destination = directory(continuation)
    if (
        destination.exists()
        or any(path.exists() for path, _ in writes)
        or any(list(ROOT.glob(f"evals/{folder}/{name}-*")) for folder in ("reports", "predictions"))
    ):
        raise ValueError("Continuation requires entirely unused destination paths")
    lineage["preserved_parent_files"] = preservation
    destination.mkdir(parents=True)
    for path, content in writes:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(content)
    for path, digest in preservation.items():
        if file_sha256(Path(path)) != digest:
            raise ValueError("Parent changed during migration; continuation must not launch")
    atomic_json(destination / "continuation.json", lineage)
    # Publish plan last. An incomplete preparation is never launchable.
    atomic_json(destination / "sequence-plan.json", continuation.model_dump(mode="json"))
    return lineage


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    parent = SequencePlan.model_validate_json(
        (plan_path(args.parent).parent / "sequence-plan.json").read_text()
    )
    lineage = migrate(parent, args.name, args.snapshot)
    print(
        json.dumps(
            {
                key: lineage[key]
                for key in ("parent", "continuation", "prefixes", "continuation_source_sha256")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
