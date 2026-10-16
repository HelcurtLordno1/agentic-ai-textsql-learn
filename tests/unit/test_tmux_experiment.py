from __future__ import annotations

from pathlib import Path

import pytest

from scripts import tmux_experiment


def test_wrapper_command_never_launches_unguarded_inference() -> None:
    plan = tmux_experiment.ExperimentPlan(
        name="a1-demo",
        suite="spider",
        variant="obligation-cpu",
        root=str(tmux_experiment.ROOT),
        report="report.json",
        predictions="predictions.jsonl",
        wrapper_args=("--profile", "acceptance-safe"),
        settings_environment={},
        dotenv_sha256=None,
    )
    command = tmux_experiment.wrapper_command(plan, 1, True)
    assert Path(command[1]).name == "run_guarded_spider.py"
    assert command[-3:] == ["--max-batches", "1", "--recovery-pilot"]


@pytest.mark.parametrize("name", ["../escape", "a:b", "a.b", "a;command", "a b", ""])
def test_session_name_cannot_escape_plan_root(name: str) -> None:
    with pytest.raises(ValueError):
        tmux_experiment.plan_path(name)


def test_resume_environment_is_frozen_and_does_not_copy_ambient_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEXT2SQL_CRITIC_MODE", "off")
    monkeypatch.setenv("TEXT2SQL_GUARDED_RUN", "true")
    monkeypatch.setattr(tmux_experiment, "dotenv_hash", lambda: None)
    plan = tmux_experiment.ExperimentPlan(
        name="a1-demo",
        suite="olist",
        variant="obligation-cpu",
        root=str(tmux_experiment.ROOT),
        report="report.json",
        predictions="predictions.jsonl",
        wrapper_args=(),
        settings_environment={"TEXT2SQL_CRITIC_MODE": "repair"},
        dotenv_sha256=None,
    )
    environment = tmux_experiment.frozen_environment(plan)
    assert environment["TEXT2SQL_CRITIC_MODE"] == "repair"
    assert "TEXT2SQL_GUARDED_RUN" not in environment
    monkeypatch.setattr(tmux_experiment, "dotenv_hash", lambda: "changed")
    with pytest.raises(ValueError, match="changed"):
        tmux_experiment.frozen_environment(plan)


def test_frozen_plan_accepts_same_checkout_via_filesystem_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = tmp_path / "checkout"
    alias.symlink_to(tmux_experiment.ROOT, target_is_directory=True)
    monkeypatch.setattr(tmux_experiment, "dotenv_hash", lambda: None)
    plan = tmux_experiment.ExperimentPlan(
        name="alias",
        suite="olist",
        variant="obligation-cpu",
        root=str(alias),
        report="report.json",
        predictions="predictions.jsonl",
        wrapper_args=(),
        settings_environment={},
        dotenv_sha256=None,
    )
    tmux_experiment.frozen_environment(plan)
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(ValueError, match="changed"):
        tmux_experiment.frozen_environment(plan.model_copy(update={"root": str(other)}))
