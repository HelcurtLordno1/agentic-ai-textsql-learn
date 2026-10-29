from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from scripts import _guarded_suite, tmux_benchmarks, tmux_experiment


def test_selection_preserves_manifest_order_and_default() -> None:
    assert _guarded_suite.select_case_ids(["a", "b", "c"], []) == ["a", "b", "c"]
    assert _guarded_suite.select_case_ids(["a", "b", "c"], ["c", "b"]) == ["b", "c"]


@pytest.mark.parametrize("selected", [["b", "b"], ["unknown"]])
def test_selection_rejects_duplicate_or_unknown_ids(selected: list[str]) -> None:
    with pytest.raises(ValueError):
        _guarded_suite.select_case_ids(["a", "b", "c"], selected)


def test_sequence_counts_only_selected_olist_cases(tmp_path: Path) -> None:
    manifest = tmp_path / "cases.jsonl"
    manifest.write_text("\n".join(json.dumps({"id": i}) for i in ["a", "b", "c"]))
    plan = tmux_experiment.ExperimentPlan(
        name="subset",
        suite="olist",
        variant="v5-contracts",
        root=str(tmp_path),
        report=str(tmp_path / "report.json"),
        predictions=str(tmp_path / "predictions.jsonl"),
        wrapper_args=("--cases", str(manifest), "--only-case-id", "c", "--only-case-id", "b"),
        settings_environment={},
        dotenv_sha256=None,
    )
    assert tmux_benchmarks.ids(plan) == ["b", "c"]
    assert "--only-case-id" in tmux_experiment.wrapper_command(plan, 1, False)


def test_guarded_subset_pause_resume_never_runs_excluded_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "cases.jsonl"
    manifest.write_text("\n".join(json.dumps({"id": i}) for i in ["a", "b", "c"]))
    predictions = tmp_path / "predictions.jsonl"
    report = tmp_path / "report.json"
    arguments = [
        "wrapper",
        "--cases",
        str(manifest),
        "--predictions",
        str(predictions),
        "--report",
        str(report),
        "--only-case-id",
        "b",
        "--only-case-id",
        "c",
    ]
    calls: list[list[str]] = []

    def fake_guard(command: list[str], **kwargs: Any) -> dict[str, Any]:
        calls.append(command)
        selected = [command[i + 1] for i, v in enumerate(command) if v == "--only-case-id"]
        assert selected == ["b", "c"]
        rows = (
            [json.loads(line) for line in predictions.read_text().splitlines()]
            if predictions.exists()
            else []
        )
        rows.append({"case_id": selected[len(rows)]})
        predictions.write_text("\n".join(json.dumps(r) for r in rows))
        if len(rows) == 2:
            report.write_text(
                json.dumps({"case_count": 2, "details": [{"id": r["case_id"]} for r in rows]})
            )
        kwargs["on_cooldown"](time.time() - 1)
        return {"samples": 2}

    monkeypatch.setattr(_guarded_suite, "guarded_process", fake_guard)
    monkeypatch.setattr(_guarded_suite, "process_group_alive", lambda pid: False)
    monkeypatch.setattr(sys, "argv", [*arguments, "--max-batches", "1"])
    _guarded_suite.main("olist")
    state = json.loads(report.with_suffix(".suite-state.json").read_text())
    assert state["completed"] == 1 and state["total"] == 2 and state["phase"] == "PAUSED"
    assert not report.exists()
    changed = [
        "wrapper",
        "--cases",
        str(manifest),
        "--predictions",
        str(predictions),
        "--report",
        str(report),
        "--only-case-id",
        "b",
    ]
    monkeypatch.setattr(sys, "argv", changed)
    with pytest.raises(SystemExit, match="configuration changed"):
        _guarded_suite.main("olist")
    assert len(calls) == 1
    monkeypatch.setattr(sys, "argv", arguments)
    _guarded_suite.main("olist")
    assert [json.loads(line)["case_id"] for line in predictions.read_text().splitlines()] == [
        "b",
        "c",
    ]
    assert json.loads(report.with_suffix(".suite-state.json").read_text())["phase"] == "COMPLETE"
    _guarded_suite.main("olist")
    assert len(calls) == 2
