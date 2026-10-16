"""Freeze source/config identity before a suite appends to a checkpoint."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from agentic_text2sql.settings import Settings


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def runtime_identity(
    settings: Settings,
    correction: bool,
    manifest: Path,
    *,
    databases: Sequence[Path] = (),
    selection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = settings.project_root
    paths = sorted(
        p
        for directory in ("src", "scripts", "configs/prompts")
        for p in (root / directory).rglob("*")
        if p.is_file() and p.suffix in {".py", ".j2", ".ps1"}
    )
    paths.extend(
        root / name
        for name in (
            "pyproject.toml",
            "uv.lock",
            "configs/models.yaml",
            "datasets/olist/business_glossary.yaml",
        )
    )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(root)).encode())
        digest.update(bytes.fromhex(file_sha256(path)))
    index_root = settings.resolved_data_dir / "indexes/p3_1_semantic"
    indexes: dict[str, str] = {}
    # Freeze both pointers and payloads. A changed index cannot be mixed into a resume.
    if index_root.exists():
        for path in sorted(p for p in index_root.rglob("*") if p.is_file()):
            indexes[str(path.relative_to(index_root))] = file_sha256(path)
    return {
        "version": "runtime-checkpoint-v2",
        "source_sha256": digest.hexdigest(),
        "manifest_sha256": file_sha256(manifest),
        "database_sha256": {str(path.resolve()): file_sha256(path) for path in databases},
        "index_sha256": indexes,
        "selection": dict(selection or {}),
        "resource_profile": os.environ.get("TEXT2SQL_RESOURCE_PROFILE"),
        "settings": settings.model_dump(
            mode="json", exclude={"project_root", "data_dir", "artifact_dir", "guarded_run"}
        ),
        "correction_enabled": correction,
    }


def freeze_checkpoint(predictions: Path, identity: dict[str, Any]) -> None:
    path = predictions.with_suffix(".runtime.json")
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != identity:
            raise ValueError(
                "Checkpoint source/config/manifest changed; choose a new prediction path"
            )
    elif predictions.exists() and predictions.stat().st_size:
        raise ValueError("Existing checkpoint has no runtime identity; cannot silently adopt it")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(path, identity)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_text(path, json.dumps(payload, sort_keys=True, indent=2) + "\n")


def atomic_text(path: Path, text: str) -> None:
    """Flush a unique temporary file before atomic replacement of a checkpoint."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if temporary is None:
            raise OSError("Checkpoint temporary file was not created")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def freeze_backend(predictions: Path, db_id: str, provenance: dict[str, object]) -> None:
    """Pin installed model/template/backend and retrieval identity per database."""
    path = predictions.with_suffix(".backend.json")
    shared_keys = (
        "pipeline_mode",
        "critic_mode",
        "generation_format",
        "generation_model",
        "generation_model_digest",
        "generation_template",
        "ollama_version",
        "ollama_options",
        "prompt_versions",
        "max_generation_requests",
        "input_token_budget",
        "output_token_budget",
        "critic_shadow_sample_rate",
        "repair_feedback_mode",
        "compute_policy",
        "deterministic_repair",
        "repairability_routing",
    )
    shared = {key: provenance.get(key) for key in shared_keys}
    previous = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.exists()
        else {"version": "backend-checkpoint-v1", "shared": shared, "databases": {}}
    )
    if not isinstance(previous, dict):
        raise ValueError("Invalid backend checkpoint")
    if previous.get("shared") != shared:
        stored = previous.get("shared")
        changed = (
            sorted(key for key in shared if stored.get(key) != shared[key])
            if isinstance(stored, dict)
            else ["shared"]
        )
        raise ValueError(
            "Checkpoint backend/model/template changed across databases: " + ", ".join(changed)
        )
    databases = previous.get("databases")
    if not isinstance(databases, dict):
        raise ValueError("Invalid backend database checkpoint")
    if db_id in databases and databases[db_id] != provenance:
        raise ValueError("Checkpoint backend/model/template changed; use a new prediction path")
    databases[db_id] = provenance
    atomic_json(path, previous)
