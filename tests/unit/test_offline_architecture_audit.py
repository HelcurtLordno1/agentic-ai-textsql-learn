from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentic_text2sql.settings import Settings
from agentic_text2sql_eval.architecture_audit import audit_saved_runs
from agentic_text2sql_eval.runtime_checkpoint import (
    freeze_backend,
    freeze_checkpoint,
    runtime_identity,
)
from agentic_text2sql_eval.spider_release import _has_order, execution_equal


def test_inventory_is_paired_and_does_not_invent_root_causes(tmp_path: Path) -> None:
    control = tmp_path / "control.json"
    treatment = tmp_path / "treatment.json"
    predictions = tmp_path / "predictions.jsonl"
    control.write_text(
        json.dumps(
            {
                "details": [
                    {
                        "id": "a",
                        "db_id": "tiny",
                        "result_correct": True,
                        "generated_sql": "SELECT 1",
                    },
                    {
                        "id": "b",
                        "db_id": "tiny",
                        "result_correct": False,
                        "generated_sql": "SELECT 2",
                    },
                ]
            }
        )
    )
    treatment.write_text(
        json.dumps(
            {
                "details": [
                    {"id": "a", "db_id": "tiny", "result_correct": False},
                    {"id": "b", "db_id": "tiny", "result_correct": True},
                ]
            }
        )
    )
    predictions.write_text(
        "\n".join(
            json.dumps(
                {
                    "case_id": case,
                    "result": {
                        "status": "SUCCEEDED",
                        "candidate": {"normalized_sql": sql},
                        "plan": {},
                        "schema_context": {},
                    },
                }
            )
            for case, sql in (("a", "SELECT 1"), ("b", "SELECT 2"))
        )
    )
    audit = audit_saved_runs(control, treatment, predictions)
    assert audit["paired"] == {"control_only": 1, "treatment_only": 1}
    assert all(r["originating_component"] == "UNKNOWN" for r in audit["records"])
    assert all(r["review_status"] == "UNREVIEWED" for r in audit["records"])
    predictions.write_text(predictions.read_text() + "\n" + predictions.read_text().splitlines()[0])
    with pytest.raises(ValueError, match="duplicate"):
        audit_saved_runs(control, treatment, predictions)


def test_checkpoint_rejects_source_config_and_manifest_changes(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    predictions = tmp_path / "prediction.jsonl"
    identity = runtime_identity(
        Settings(PROJECT_ROOT=root, TEXT2SQL_PIPELINE_MODE="a1"), False, manifest
    )
    freeze_checkpoint(predictions, identity)
    freeze_checkpoint(predictions, identity)
    changed = runtime_identity(
        Settings(PROJECT_ROOT=root, TEXT2SQL_PIPELINE_MODE="p6"), False, manifest
    )
    with pytest.raises(ValueError, match="changed"):
        freeze_checkpoint(predictions, changed)
    legacy = tmp_path / "legacy.jsonl"
    legacy.write_text('{"case_id":"a"}\n')
    with pytest.raises(ValueError, match="no runtime identity"):
        freeze_checkpoint(legacy, identity)


def test_evaluator_v2_outer_order_and_existing_comparison_semantics() -> None:
    # V2 makes outer ordering authoritative; inner ORDER BY cannot order a result.
    assert not _has_order("SELECT x FROM (SELECT x FROM t ORDER BY x)")
    assert _has_order("SELECT x FROM t ORDER BY x")
    assert not execution_equal([[1], [1]], [[1], [2]], ordered=False)
    assert execution_equal([[None], [1]], [[1], [None]], ordered=False)
    assert not execution_equal([[None]], [["None"]], ordered=False)
    assert execution_equal([[1.0000001]], [[1.0000002]], ordered=False)
    assert execution_equal([], [], ordered=False)
    assert not execution_equal([[1, 2]], [[1]], ordered=False)


def test_checkpoint_detects_database_selection_and_template_changes(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    settings = Settings(PROJECT_ROOT=root, TEXT2SQL_DATA_DIR=tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    database = tmp_path / "placeholder.sqlite"
    database.write_bytes(b"first-identity")
    predictions = tmp_path / "predictions.jsonl"
    identity = runtime_identity(
        settings, False, manifest, databases=[database], selection={"case_ids": ["a"]}
    )
    freeze_checkpoint(predictions, identity)
    database.write_bytes(b"changed-identity")
    changed = runtime_identity(
        settings, False, manifest, databases=[database], selection={"case_ids": ["a"]}
    )
    with pytest.raises(ValueError, match="changed"):
        freeze_checkpoint(predictions, changed)
    freeze_backend(predictions, "tiny", {"template_sha256": "first"})
    freeze_backend(predictions, "tiny", {"template_sha256": "first"})
    with pytest.raises(ValueError, match="template changed"):
        freeze_backend(predictions, "tiny", {"template_sha256": "second"})
    other = tmp_path / "other.jsonl"
    freeze_backend(other, "first-db", {"ollama_version": "first-version"})
    with pytest.raises(ValueError, match="across databases"):
        freeze_backend(other, "second-db", {"ollama_version": "changed-version"})
