"""Manage one frozen, guarded experiment in tmux; no direct inference entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentic_text2sql.hardware import ProfileName
from agentic_text2sql.settings import Settings
from agentic_text2sql_eval.runtime_checkpoint import atomic_json, file_sha256
from agentic_text2sql_eval.suite_control import SuiteState

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "data/artifacts/experiments"
VARIANTS: dict[str, dict[str, str]] = {
    "p6": {"TEXT2SQL_PIPELINE_MODE": "p6", "TEXT2SQL_CRITIC_MODE": "off"},
    "a1-off": {"TEXT2SQL_PIPELINE_MODE": "a1", "TEXT2SQL_CRITIC_MODE": "off"},
    "a1-shadow": {"TEXT2SQL_PIPELINE_MODE": "a1", "TEXT2SQL_CRITIC_MODE": "shadow"},
    "a1-legacy-repair": {
        "TEXT2SQL_PIPELINE_MODE": "a1",
        "TEXT2SQL_CRITIC_MODE": "repair",
        "TEXT2SQL_COMPUTE_POLICY": "legacy",
        "TEXT2SQL_DETERMINISTIC_REPAIR": "false",
    },
    "obligation-llm": {
        "TEXT2SQL_PIPELINE_MODE": "a1",
        "TEXT2SQL_CRITIC_MODE": "repair",
        "TEXT2SQL_COMPUTE_POLICY": "obligation",
        "TEXT2SQL_DETERMINISTIC_REPAIR": "false",
    },
    "obligation-cpu": {
        "TEXT2SQL_PIPELINE_MODE": "a1",
        "TEXT2SQL_CRITIC_MODE": "repair",
        "TEXT2SQL_COMPUTE_POLICY": "obligation",
        "TEXT2SQL_DETERMINISTIC_REPAIR": "true",
    },
    "obligation-risk": {
        "TEXT2SQL_PIPELINE_MODE": "a1",
        "TEXT2SQL_CRITIC_MODE": "repair",
        "TEXT2SQL_COMPUTE_POLICY": "obligation",
        "TEXT2SQL_DETERMINISTIC_REPAIR": "false",
        "TEXT2SQL_REPAIRABILITY_ROUTING": "false",
    },
    "obligation-risk-cpu": {
        "TEXT2SQL_PIPELINE_MODE": "a1",
        "TEXT2SQL_CRITIC_MODE": "repair",
        "TEXT2SQL_COMPUTE_POLICY": "obligation",
        "TEXT2SQL_DETERMINISTIC_REPAIR": "true",
        "TEXT2SQL_REPAIRABILITY_ROUTING": "false",
    },
}


class ExperimentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal["tmux-plan-v1"] = "tmux-plan-v1"
    name: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    suite: Literal["spider", "olist"]
    variant: str
    root: str
    report: str
    predictions: str
    python_executable: str = Field(default_factory=lambda: sys.executable)
    python_version: str = Field(default_factory=lambda: sys.version)
    wrapper_args: tuple[str, ...]
    settings_environment: dict[str, str]
    dotenv_sha256: str | None


def plan_path(name: str) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", name):
        raise ValueError("Session name must use letters, digits, underscores or hyphens")
    return PLANS / name / "plan.json"


def dotenv_hash() -> str | None:
    path = ROOT / ".env"
    return file_sha256(path) if path.exists() else None


def create_plan(
    args: argparse.Namespace,
    *,
    settings_overrides: dict[str, str] | None = None,
) -> ExperimentPlan:
    overrides = {
        "TEXT2SQL_COMPUTE_POLICY": "legacy",
        "TEXT2SQL_DETERMINISTIC_REPAIR": "false",
        "TEXT2SQL_REPAIRABILITY_ROUTING": "true",
        **VARIANTS[args.variant],
        **(settings_overrides or {}),
    }
    settings = Settings(**overrides)
    # Only typed settings are persisted, never the process environment or API secrets.
    if not settings.project_root.samefile(ROOT):
        raise ValueError("PROJECT_ROOT must match this checkout")
    # DrvFS accepts case aliases. Freeze this spelling for database/index identity.
    settings = settings.model_copy(update={"project_root": ROOT})
    environment: dict[str, str] = {}
    for field, definition in Settings.model_fields.items():
        if field in {"guarded_run", "ollama_num_gpu"}:
            continue  # The guarded wrapper owns these values.
        value = settings.model_dump(mode="json", by_alias=True)[definition.alias or field]
        if value is not None:
            environment[definition.alias or field] = (
                json.dumps(value) if isinstance(value, bool) else str(value)
            )
    predictions = args.predictions.resolve()
    report = args.report.resolve()
    wrapper = [
        "--profile",
        args.profile,
        "--predictions",
        str(predictions),
        "--report",
        str(report),
        "--batch-size",
        "1",
        "--cooldown-seconds",
        "60",
        "--correction"
        if args.variant
        in {
            "p6",
            "a1-legacy-repair",
            "obligation-llm",
            "obligation-cpu",
            "obligation-risk",
            "obligation-risk-cpu",
        }
        else "--no-correction",
    ]
    if args.suite == "spider":
        if args.manifest is None:
            raise ValueError("Spider requires --manifest")
        wrapper.extend(["--manifest", str(args.manifest.resolve())])
        if args.allow_dirty_source:
            wrapper.append("--allow-dirty-source")
    else:
        cases = args.cases or ROOT / "evals/configs/olist-acceptance-60.jsonl"
        wrapper.extend(["--cases", str(cases.resolve()), "--evaluation-id", args.name])
    return ExperimentPlan(
        name=args.name,
        suite=args.suite,
        variant=args.variant,
        root=str(ROOT),
        report=str(report),
        predictions=str(predictions),
        wrapper_args=tuple(wrapper),
        settings_environment=environment,
        dotenv_sha256=dotenv_hash(),
    )


def frozen_environment(plan: ExperimentPlan) -> dict[str, str]:
    if not Path(plan.root).samefile(ROOT) or plan.dotenv_sha256 != dotenv_hash():
        raise ValueError("Checkout location or .env changed; use a new experiment name/paths")
    if plan.python_version != sys.version or not Path(plan.python_executable).samefile(
        sys.executable
    ):
        raise ValueError("Python interpreter changed; use the original locked environment")
    environment = dict(os.environ)
    for field, definition in Settings.model_fields.items():
        environment.pop(definition.alias or field, None)
    environment.pop("TEXT2SQL_RESOURCE_PROFILE", None)
    environment.update(plan.settings_environment)
    return environment


def wrapper_command(plan: ExperimentPlan, max_batches: int | None, pilot: bool) -> list[str]:
    script = "run_guarded_spider.py" if plan.suite == "spider" else "run_guarded_acceptance.py"
    command = [plan.python_executable, str(ROOT / "scripts" / script), *plan.wrapper_args]
    if max_batches is not None:
        command.extend(["--max-batches", str(max_batches)])
    if pilot:
        command.append("--recovery-pilot")
    return command


def tmux(*arguments: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    if shutil.which("tmux") is None:
        raise ValueError("tmux is not installed; install it in WSL before launching")
    return subprocess.run(
        ["tmux", *arguments],
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def session_exists(name: str) -> bool:
    try:
        tmux("has-session", "-t", f"={name}", capture=True)
        return True
    except subprocess.CalledProcessError:
        return False


def launch(plan: ExperimentPlan, max_batches: int | None, pilot: bool) -> None:
    frozen_environment(plan)  # Validate before creating a tmux session.
    stop_path = Path(plan.report).with_suffix(".resource-stop.json")
    if stop_path.exists():
        raise ValueError(f"Resource stop is latched: {stop_path}; no automatic override")
    path = plan_path(plan.name)
    command = [
        plan.python_executable,
        str(Path(__file__).resolve()),
        "execute",
        "--plan",
        str(path),
    ]
    if max_batches is not None:
        command.extend(["--max-batches", str(max_batches)])
    if pilot:
        command.append("--recovery-pilot")
    target = f"{plan.name}:0.0"
    # exec makes the supervised command own the pane; a dead pane can be respawned.
    shell_command = "exec " + shlex.join(command)
    if session_exists(plan.name):
        dead = tmux(
            "display-message", "-p", "-t", target, "#{pane_dead}", capture=True
        ).stdout.strip()
        if dead != "1":
            print(f"Session already active; attach with: tmux attach -t {plan.name}")
            return
        Path(plan.report).with_suffix(".pause-request.json").unlink(missing_ok=True)
        tmux("respawn-pane", "-t", target, "-c", str(ROOT), shell_command)
    else:
        Path(plan.report).with_suffix(".pause-request.json").unlink(missing_ok=True)
        tmux("new-session", "-d", "-s", plan.name, "-c", str(ROOT))
        tmux("set-option", "-w", "-t", target, "remain-on-exit", "on")
        tmux("send-keys", "-t", target, "-l", shell_command)
        tmux("send-keys", "-t", target, "Enter")
    print(f"Started {plan.name}; attach: tmux attach -t {plan.name}")
    print(f"Detach: Ctrl+b then d. Durable log: {path.parent / 'run.log'}")


def execute(plan: ExperimentPlan, max_batches: int | None, pilot: bool) -> int:
    environment = frozen_environment(plan)
    log = plan_path(plan.name).parent / "run.log"
    with log.open("a", encoding="utf-8", buffering=1) as output:
        child = subprocess.Popen(
            wrapper_command(plan, max_batches, pilot),
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        def request_pause(signum: int, frame: object) -> None:
            del signum, frame
            # A file request works even during wrapper initialization. The current
            # guarded child finishes, checkpoints, unloads and cools down first.
            atomic_json(Path(plan.report).with_suffix(".pause-request.json"), {"pause": True})

        old_handlers = {
            sig: signal.signal(sig, request_pause) for sig in (signal.SIGINT, signal.SIGTERM)
        }
        try:
            if child.stdout is None:
                raise RuntimeError("Missing wrapper output pipe")
            for line in child.stdout:
                output.write(line)
                print(line, end="", flush=True)
            code = child.wait()
            message = (
                f"Wrapper exit code: {code}; inspect status/report before treating it as complete\n"
            )
            output.write(message)
            print(message, end="", flush=True)
            return code
        finally:
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
            if child.stdout is not None:
                child.stdout.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser("run")
    run.add_argument("--name", required=True)
    run.add_argument("--suite", choices=["spider", "olist"], required=True)
    run.add_argument("--variant", choices=VARIANTS, default="obligation-cpu")
    run.add_argument("--profile", choices=[p.value for p in ProfileName], default="acceptance-safe")
    run.add_argument("--manifest", type=Path)
    run.add_argument("--cases", type=Path)
    run.add_argument("--predictions", type=Path, required=True)
    run.add_argument("--report", type=Path, required=True)
    run.add_argument("--allow-dirty-source", action="store_true")
    run.add_argument("--max-batches", type=int)
    for name in ("resume", "pause", "attach", "status"):
        sub = commands.add_parser(name)
        sub.add_argument("--name", required=True)
        if name == "resume":
            sub.add_argument("--max-batches", type=int)
            sub.add_argument("--recovery-pilot", action="store_true")
    worker = commands.add_parser("execute")
    worker.add_argument("--plan", type=Path, required=True)
    worker.add_argument("--max-batches", type=int)
    worker.add_argument("--recovery-pilot", action="store_true")
    args = parser.parse_args()
    if getattr(args, "max_batches", None) is not None and args.max_batches < 1:
        parser.error("max-batches must be positive")
    os.chdir(ROOT)
    try:
        if args.action == "run":
            path = plan_path(args.name)
            if path.exists():
                raise ValueError(
                    "Plan already exists: use resume, or a new name and artifact paths"
                )
            plan = create_plan(args)
            if Path(plan.predictions).exists() or Path(plan.report).exists():
                raise ValueError("New experiment requires unused prediction/report paths")
            if session_exists(plan.name):
                raise ValueError("tmux session name already exists; choose a new name")
            atomic_json(path, plan.model_dump(mode="json"))
            launch(plan, args.max_batches, False)
        elif args.action == "execute":
            plan = ExperimentPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
            if args.plan.resolve() != plan_path(plan.name).resolve():
                raise ValueError("Execution requires the canonical frozen plan path")
            raise SystemExit(execute(plan, args.max_batches, args.recovery_pilot))
        else:
            plan = ExperimentPlan.model_validate_json(
                plan_path(args.name).read_text(encoding="utf-8")
            )
            if args.action == "resume":
                launch(plan, args.max_batches, args.recovery_pilot)
            elif args.action == "attach":
                tmux("attach-session", "-t", f"={plan.name}")
            elif args.action == "pause":
                atomic_json(Path(plan.report).with_suffix(".pause-request.json"), {"pause": True})
                print("Pause requested: wait for current case checkpoint, unload and 60s cooldown")
            else:
                state = Path(plan.report).with_suffix(".suite-state.json")
                if state.exists():
                    print(
                        SuiteState.model_validate_json(state.read_text()).model_dump_json(indent=2)
                    )
                else:
                    print("No suite state yet; inspect tmux pane and run.log")
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
