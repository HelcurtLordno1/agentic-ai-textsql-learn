from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path

import pytest

from agentic_text2sql.hardware import PROFILES, ProfileName
from agentic_text2sql.settings import Settings
from agentic_text2sql_eval.runtime_checkpoint import atomic_json, file_sha256, runtime_identity
from scripts import migrate_sensor_checkpoint as migration
from scripts import tmux_experiment
from scripts.tmux_benchmarks import SequencePlan, SequenceState, directory
from scripts.tmux_experiment import ExperimentPlan


@pytest.fixture
def parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(migration, "ROOT", tmp_path)
    monkeypatch.setattr(tmux_experiment, "ROOT", tmp_path)
    monkeypatch.setattr(tmux_experiment, "PLANS", tmp_path / "data/artifacts/experiments")
    monkeypatch.setattr(migration.subprocess, "check_output", lambda *a, **k: "abc123\n")
    profile = PROFILES[ProfileName.QWEN_CPU_600_STABLE]
    monkeypatch.setenv("TEXT2SQL_RESOURCE_PROFILE", profile.model_dump_json())
    for name in (*migration.FIXED_FILES, "src/agentic_text2sql/hardware.py"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("original")
    snapshot = tmp_path / "frozen.tar.gz"
    with tarfile.open(snapshot, "w:gz") as archive:
        for path in sorted(tmp_path.rglob("*")):
            if path.is_file() and path != snapshot:
                archive.add(path, arcname=str(path.relative_to(tmp_path)))
    settings_environment = {"PROJECT_ROOT": str(tmp_path)}
    settings = Settings(**{**settings_environment, **profile.ollama_environment()})
    database = tmp_path / "database.sqlite"
    database.write_bytes(b"immutable database")
    children = []
    for kind in ("spider", "olist"):
        manifest = tmp_path / f"{kind}.manifest.json"
        manifest.write_text(json.dumps({"cases": [{"id": "a"}, {"id": "b"}]}))
        if kind == "olist":
            manifest.write_text('{"id":"a"}\n{"id":"b"}\n')
        predictions = tmp_path / f"evals/predictions/parent-{kind}.jsonl"
        report = tmp_path / f"evals/reports/parent-{kind}.json"
        predictions.parent.mkdir(parents=True, exist_ok=True)
        report.parent.mkdir(parents=True, exist_ok=True)
        predictions.write_text(
            json.dumps(
                {
                    "case_id": "a",
                    "result": {
                        "run_id": "one",
                        "question": "synthetic",
                        "status": "SUCCEEDED",
                        "route_reason": "test",
                        "prompt_versions": {},
                    },
                }
            )
            + "\n"
        )
        child = ExperimentPlan(
            name=f"parent-{kind}",
            suite=kind,
            variant="v4-reliability",
            root=str(tmp_path),
            predictions=str(predictions),
            report=str(report),
            dotenv_sha256=None,
            settings_environment=settings_environment,
            wrapper_args=(
                "--manifest" if kind == "spider" else "--cases",
                str(manifest),
                "--predictions",
                str(predictions),
                "--report",
                str(report),
            ),
        )
        children.append(child)
        atomic_json(
            predictions.with_suffix(".runtime.json"),
            runtime_identity(settings, True, manifest, databases=[database]),
        )
        atomic_json(predictions.with_suffix(".backend.json"), {"frozen": "backend"})
        atomic_json(
            report.with_suffix(".suite-state.json"),
            {
                "child_pid": None,
                "cleanup_pending": False,
            },
        )
        if kind == "spider":
            atomic_json(
                predictions.with_suffix(".provenance.json"),
                {
                    "git_commit": "abc123",
                    "run_config": {},
                },
            )
            atomic_json(
                report.with_suffix(".resource-stop.json"),
                {
                    "reason": (
                        "monitor failure: TimeoutExpired: nvidia-smi timed out after 0.5 seconds"
                    ),
                    "samples": 0,
                    "observed_peak": None,
                    "cleanup_error": None,
                    "resource_stop": True,
                },
            )
    parent = SequencePlan(
        name="parent",
        spider=children[0],
        olist=children[1],
        models_dir=str(tmp_path),
        profile=profile.name,
    )
    atomic_json(directory(parent) / "sequence-plan.json", parent.model_dump(mode="json"))
    atomic_json(
        directory(parent) / "sequence-state.json",
        SequenceState(
            phase="RESOURCE_STOP", boot_id="test", completed={"spider": 1, "olist": 1}
        ).model_dump(mode="json"),
    )
    (tmp_path / "src/agentic_text2sql/hardware.py").write_text("sensor transport fix")
    return parent, snapshot, tmp_path


def test_continuation_preserves_prefix_and_incident_with_explicit_lineage(parent) -> None:
    plan, snapshot, root = parent
    original = {p: file_sha256(p) for p in root.rglob("*") if p.is_file()}
    evidence = migration.migrate(plan, "continued", snapshot)
    assert evidence["prefixes"]["spider"]["count"] == 1
    for path, digest in original.items():
        assert file_sha256(path) == digest
    new_dir = root / "data/artifacts/experiments/continued"
    child = SequencePlan.model_validate_json((new_dir / "sequence-plan.json").read_text())
    for old, new in zip(plan.benchmarks, child.benchmarks, strict=True):
        assert Path(new.predictions).read_bytes() == Path(old.predictions).read_bytes()
        old_runtime = json.loads(Path(old.predictions).with_suffix(".runtime.json").read_text())
        new_runtime = json.loads(Path(new.predictions).with_suffix(".runtime.json").read_text())
        assert new_runtime == {
            **old_runtime,
            "source_sha256": evidence["continuation_source_sha256"],
        }
    assert (new_dir / "continuation.json").exists()
    assert not (new_dir / "sequence-state.json").exists()  # No inference/pilot fabricated.
    with pytest.raises(ValueError, match="unused"):
        migration.migrate(plan, "continued", snapshot)


@pytest.mark.parametrize("failure", ["generation", "data", "prefix", "power", "owner"])
def test_migration_refuses_semantic_drift_bad_prefix_and_unremediated_stops(
    parent, failure
) -> None:
    plan, snapshot, root = parent
    if failure == "generation":
        (root / "src/generator.py").write_text("changed prompt")
    elif failure == "data":
        (root / "database.sqlite").write_bytes(b"different data")
    elif failure == "prefix":
        Path(plan.spider.predictions).write_text('{"case_id":"b"}\n')
    elif failure == "power":
        atomic_json(
            Path(plan.spider.report).with_suffix(".resource-stop.json"),
            {
                "reason": "GPU power 73.4 W",
                "resource_stop": True,
            },
        )
    else:
        state_path = directory(plan) / "sequence-state.json"
        state = json.loads(state_path.read_text())
        state["server_pid"] = 42
        atomic_json(state_path, state)
    with pytest.raises(ValueError):
        migration.migrate(plan, "continued", snapshot)
    assert not (root / "data/artifacts/experiments/continued").exists()


def test_source_digest_is_content_sensitive_and_all_fixed_inputs_are_pinned() -> None:
    files = {name: hashlib.sha256(name.encode()).hexdigest() for name in migration.FIXED_FILES}
    first = migration.source_digest(files)
    files["src/agentic_text2sql/gpu_monitor.py"] = "0" * 64
    assert migration.source_digest(files) != first
