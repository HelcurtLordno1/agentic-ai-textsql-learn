from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from scripts import _guarded_suite


def test_pause_resume_preserves_prefix_and_success_requires_final_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "manifest.json"
    predictions = tmp_path / "predictions.jsonl"
    report = tmp_path / "report.json"
    manifest.write_text(json.dumps({"case_count": 2, "cases": [{"id": "a"}, {"id": "b"}]}))
    arguments = [
        "run_guarded_spider.py",
        "--manifest",
        str(manifest),
        "--predictions",
        str(predictions),
        "--report",
        str(report),
    ]
    calls = []

    def fake_guard(command: list[str], **kwargs: Any) -> dict[str, Any]:
        calls.append(command)
        assert kwargs["cooldown_seconds"] == 60
        kwargs["on_spawn"](12345)
        ids = (
            [json.loads(line)["case_id"] for line in predictions.read_text().splitlines()]
            if predictions.exists()
            else []
        )
        if len(ids) < 2:
            ids.append(["a", "b"][len(ids)])
            predictions.write_text("\n".join(json.dumps({"case_id": value}) for value in ids))
        if len(ids) == 2:
            report.write_text(
                json.dumps({"case_count": 2, "details": [{"id": value} for value in ids]})
            )
        kwargs["on_cooldown"](time.time() - 1)
        return {"samples": 2}

    monkeypatch.setattr(_guarded_suite, "guarded_process", fake_guard)
    monkeypatch.setattr(_guarded_suite, "process_group_alive", lambda pid: False)
    monkeypatch.setattr(sys, "argv", [*arguments, "--max-batches", "1"])
    _guarded_suite.main("spider")
    state = json.loads(report.with_suffix(".suite-state.json").read_text())
    assert state["phase"] == "PAUSED" and state["completed"] == 1
    assert not report.exists()
    assert "SUCCESS FINISH ALL" not in capsys.readouterr().out

    # An unclean/rebooted state cannot resume directly, even with a valid prefix.
    state["phase"] = "RUNNING"
    state["boot_id"] = "different-boot"
    report.with_suffix(".suite-state.json").write_text(json.dumps(state))
    monkeypatch.setattr(sys, "argv", arguments)
    with pytest.raises(SystemExit, match="Unclean"):
        _guarded_suite.main("spider")
    assert len(calls) == 1

    monkeypatch.setattr(sys, "argv", [*arguments, "--recovery-pilot"])
    _guarded_suite.main("spider")
    state = json.loads(report.with_suffix(".suite-state.json").read_text())
    assert state["phase"] == "COMPLETE" and state["completed"] == 2
    assert "SUCCESS FINISH ALL: 2/2" in capsys.readouterr().out
    assert len(calls) == 2
    assert [json.loads(line)["case_id"] for line in predictions.read_text().splitlines()] == [
        "a",
        "b",
    ]

    # Repeating resume after completion never schedules another batch.
    monkeypatch.setattr(sys, "argv", arguments)
    _guarded_suite.main("spider")
    assert len(calls) == 2
    report.with_suffix(".resource-stop.json").write_text("{}")
    with pytest.raises(SystemExit, match="latched"):
        _guarded_suite.main("spider")
    assert len(calls) == 2
