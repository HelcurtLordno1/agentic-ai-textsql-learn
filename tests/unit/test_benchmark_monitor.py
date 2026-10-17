from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import benchmark_monitor, tmux_benchmarks
from scripts.tmux_experiment import ExperimentPlan


def make_plan(tmp_path: Path) -> tmux_benchmarks.SequencePlan:
    spider = tmp_path / "spider.json"
    olist = tmp_path / "olist.jsonl"
    spider.write_text(json.dumps({"cases": [{"id": "s1"}, {"id": "s2"}]}))
    olist.write_text('{"id":"o1"}\n{"id":"o2"}\n')
    children = []
    for suite, manifest, flag in [("spider", spider, "--manifest"), ("olist", olist, "--cases")]:
        children.append(
            ExperimentPlan(
                name=f"test-{suite}",
                suite=suite,
                variant="v4-reliability",
                root=str(tmp_path),
                report=str(tmp_path / f"{suite}-report.json"),
                predictions=str(tmp_path / f"{suite}-predictions.jsonl"),
                wrapper_args=(flag, str(manifest)),
                settings_environment={},
                dotenv_sha256=None,
            )
        )
    return tmux_benchmarks.SequencePlan(
        name="test", spider=children[0], olist=children[1], models_dir=str(tmp_path)
    )


def write_state(tmp_path: Path, **changes) -> None:
    state = tmux_benchmarks.SequenceState(
        phase="RUNNING",
        boot_id=benchmark_monitor.boot_id(),
        server_pid=123,
        worker_pid=456,
        completed={"spider": 1, "olist": 1},
        **changes,
    )
    (tmp_path / "sequence-state.json").write_text(state.model_dump_json())


def test_monitor_survives_worker_stop_and_latch_overrides_running_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = make_plan(tmp_path)
    write_state(tmp_path)
    monkeypatch.setattr(benchmark_monitor, "process_alive", lambda pid: True)
    latch = Path(plan.spider.report).with_suffix(".resource-stop.json")
    latch.write_text('{"reason":"GPU power 73.4 W"}')
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}
    text = benchmark_monitor.render(plan, tmp_path)
    assert text.splitlines()[0] == "test | RESOURCE_STOP"
    assert "73.4 W" in text and "spider: 1/2" in text and "WORKLOAD STOPPED" in text
    assert {p: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_bad_state_and_absent_server_are_not_healthy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = make_plan(tmp_path)
    assert "test | STARTING" in benchmark_monitor.render(plan, tmp_path)
    (tmp_path / "sequence-state.json").write_text("broken")
    assert "test | UNKNOWN" in benchmark_monitor.render(plan, tmp_path)
    write_state(tmp_path)
    monkeypatch.setattr(benchmark_monitor, "process_alive", lambda pid: False)
    assert "test | UNKNOWN" in benchmark_monitor.render(plan, tmp_path)
    latch = tmp_path / "server.resource-stop.json"
    latch.write_text("broken")
    assert "test | RESOURCE_STOP" in benchmark_monitor.render(plan, tmp_path)


def test_pause_waits_for_cleanup_and_complete_requires_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = make_plan(tmp_path)
    state = tmux_benchmarks.SequenceState(
        phase="PAUSED", boot_id=benchmark_monitor.boot_id(), server_pid=123
    )
    path = tmp_path / "sequence-state.json"
    path.write_text(state.model_dump_json())
    monkeypatch.setattr(benchmark_monitor, "process_alive", lambda pid: pid is not None)
    assert "test | PAUSING" in benchmark_monitor.render(plan, tmp_path)
    state.server_pid = None
    path.write_text(state.model_dump_json())
    assert "test | PAUSED" in benchmark_monitor.render(plan, tmp_path)
    state.phase = "COMPLETE"
    path.write_text(state.model_dump_json())
    assert "test | UNKNOWN" in benchmark_monitor.render(plan, tmp_path)
    for child in plan.benchmarks:
        Path(child.report).write_text(
            json.dumps(
                {"case_count": 2, "details": [{"id": i} for i in tmux_benchmarks.ids(child)]}
            )
        )
    assert "test | COMPLETE" in benchmark_monitor.render(plan, tmp_path)


def test_tail_is_bounded_even_for_large_logs(tmp_path: Path) -> None:
    p = tmp_path / "run.log"
    p.write_text("old\n" * 10000 + "latest\n")
    assert benchmark_monitor.tail(p, lines=2) == "old\nlatest"


def test_independent_monitor_window_is_created_and_selected_without_resuming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = make_plan(tmp_path)
    calls = []
    monkeypatch.setattr(tmux_benchmarks, "directory", lambda p: tmp_path)

    def tmux(*args, **kwargs):
        calls.append(args)
        # Missing-window display-message can return the current dead pane.
        if args[0] == "list-windows":
            return SimpleNamespace(stdout="worker\n")
        return SimpleNamespace(stdout="1")

    monkeypatch.setattr(tmux_benchmarks, "tmux", tmux)
    tmux_benchmarks.ensure_monitor(plan)
    created = next(c for c in calls if c[0] == "new-window")
    assert "scripts.benchmark_monitor" in created[-1]
    assert "execute" not in created[-1] and "resume" not in created[-1]
    assert calls[-1] == ("select-window", "-t", "test:monitor")


def test_long_tracebacks_cannot_scroll_stop_reason_and_checkpoint_off_screen(
    tmp_path: Path,
) -> None:
    plan = make_plan(tmp_path)
    write_state(tmp_path)
    (tmp_path / "server.resource-stop.json").write_text('{"reason":"GPU power 73.4 W"}')
    (tmp_path / "run.log").write_text(("trace " * 1000 + "\n") * 40)
    lines = benchmark_monitor.render(plan, tmp_path, width=80, height=24).splitlines()
    assert len(lines) < 24 and max(map(len, lines)) <= 80
    assert lines[0] == "test | RESOURCE_STOP"
    assert "73.4 W" in "\n".join(lines) and "spider: 1/2" in "\n".join(lines)
