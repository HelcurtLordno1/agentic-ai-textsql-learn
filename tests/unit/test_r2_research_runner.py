from pathlib import Path

import pytest

from scripts.run_r2_olist_research import (
    ensure_provenance,
    guarded_command,
    source_digest,
    stop_lock_message,
    write_pipeline_status,
)


def test_source_digest_ignores_runtime_cache_but_locks_source(tmp_path: Path) -> None:
    source = tmp_path / "src/package/module.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    for path in (
        tmp_path / "configs/config.yaml",
        tmp_path / "datasets/olist/semantic_catalog.yaml",
        tmp_path / "evals/configs/olist-acceptance-60.jsonl",
        tmp_path / "scripts/run_guarded_acceptance.py",
        tmp_path / "scripts/run_olist_acceptance.py",
        tmp_path / "scripts/run_r2_olist_research.py",
        tmp_path / "scripts/run_r2_olist_recovery.py",
        tmp_path / "scripts/serve_ollama_guarded.py",
        tmp_path / "scripts/launch_r2_olist_tmux.py",
        tmp_path / "scripts/certify_shadow_proofs.py",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stable\n", encoding="utf-8")
    first = source_digest(tmp_path)
    cache = tmp_path / "src/package/__pycache__/module.pyc"
    cache.parent.mkdir()
    cache.write_bytes(b"runtime cache")
    assert source_digest(tmp_path) == first
    source.write_text("VALUE = 2\n", encoding="utf-8")
    assert source_digest(tmp_path) != first


def test_provenance_refuses_resume_after_source_change(tmp_path: Path) -> None:
    path = tmp_path / "run.provenance.json"
    ensure_provenance(path, {"source_digest": "one"})
    ensure_provenance(path, {"source_digest": "one"})
    with pytest.raises(SystemExit, match="SOURCE_LOCK_MISMATCH"):
        ensure_provenance(path, {"source_digest": "two"})


def test_pipeline_status_is_atomically_replaced(tmp_path: Path) -> None:
    path = tmp_path / "run.pipeline-status.json"
    write_pipeline_status(path, {"state": "running", "phase": "shadow"})
    write_pipeline_status(path, {"state": "complete", "phase": "enforce"})

    assert path.read_text(encoding="utf-8") == (
        '{\n  "phase": "enforce",\n  "state": "complete"\n}\n'
    )
    assert not path.with_suffix(".json.tmp").exists()


def test_guarded_command_hard_codes_ultrasafe_limits(tmp_path: Path) -> None:
    command = guarded_command(
        tmp_path,
        evaluation_id="r2-test",
        predictions=tmp_path / "predictions.jsonl",
        report=tmp_path / "report.json",
        progress=tmp_path / "progress.json",
        stop_record=tmp_path / "stop.json",
        partitions=("dev", "regression"),
        max_batches=1,
    )
    joined = " ".join(command)
    assert "--profile olist-paper1-ultrasafe" in joined
    assert "--batch-size 1" in joined
    assert "--cooldown-seconds 60" in joined
    assert "--sample-seconds 0.5" in joined
    assert "--batch-timeout-seconds 360" in joined
    assert "--stop-record" in joined
    assert "--partition dev --partition regression" in joined
    assert "--max-batches 1" in joined


def test_guarded_command_can_select_sparse_case_ids(tmp_path: Path) -> None:
    command = guarded_command(
        tmp_path,
        evaluation_id="r2-recovery",
        predictions=tmp_path / "predictions.jsonl",
        report=tmp_path / "report.json",
        progress=tmp_path / "progress.json",
        case_ids=("case_002", "case_009"),
    )

    joined = " ".join(command)
    assert "--only-case-id case_002 --only-case-id case_009" in joined


def test_stop_lock_message_exposes_reason_and_checkpoint(tmp_path: Path) -> None:
    path = tmp_path / "stop.json"
    path.write_text(
        '{"reason":"GPU graphics clock 1215 MHz","checkpoint":0,"total_cases":45}\n',
        encoding="utf-8",
    )

    message = stop_lock_message(path)

    assert message is not None
    assert "GPU graphics clock 1215 MHz" in message
    assert "checkpoint=0/45" in message
