"""One tmux session: two guarded pilots, then Spider and Olist sequentially."""

from __future__ import annotations

import argparse
import json
import queue
import shlex
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Literal, TextIO

import httpx
from pydantic import BaseModel, ConfigDict, Field

from agentic_text2sql.hardware import PROFILES, ProfileName
from agentic_text2sql.resource_guard import _stop, workload_lease
from agentic_text2sql_eval.runtime_checkpoint import atomic_json
from agentic_text2sql_eval.suite_control import (
    SuiteState,
    boot_id,
    prediction_prefix,
    process_group_alive,
    require_complete_report,
)
from scripts.tmux_experiment import (
    ROOT,
    VARIANTS,
    ExperimentPlan,
    create_plan,
    frozen_environment,
    plan_path,
    session_exists,
    tmux,
    wrapper_command,
)


class SequencePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal["benchmark-sequence-v1"] = "benchmark-sequence-v1"
    name: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,48}$")
    spider: ExperimentPlan
    olist: ExperimentPlan
    models_dir: str
    profile: ProfileName = ProfileName.CLOCK_CAPPED
    server_port: int = Field(default=11435, ge=1024, le=65535)
    backend_port: int = Field(default=11436, ge=1024, le=65535)

    @property
    def benchmarks(self) -> tuple[ExperimentPlan, ExperimentPlan]:
        return self.spider, self.olist


class SequenceState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phase: Literal["PREPARING", "PILOT", "RUNNING", "PAUSED", "COMPLETE", "FAILED", "RESOURCE_STOP"]
    boot_id: str
    pilot_passed: dict[str, bool] = Field(default_factory=dict)
    recovery_required: bool = False
    active_benchmark: str | None = None
    worker_pid: int | None = None
    server_pid: int | None = None
    proxy_pid: int | None = None
    completed: dict[str, int] = Field(default_factory=dict)
    reason: str | None = None


def directory(plan: SequencePlan) -> Path:
    return plan_path(plan.name).parent


def save(plan: SequencePlan, state: SequenceState) -> None:
    atomic_json(directory(plan) / "sequence-state.json", state.model_dump(mode="json"))


def ids(plan: ExperimentPlan) -> list[str]:
    flag = "--manifest" if plan.suite == "spider" else "--cases"
    manifest = Path(plan.wrapper_args[plan.wrapper_args.index(flag) + 1])
    content = manifest.read_text(encoding="utf-8")
    cases = (
        json.loads(content)["cases"]
        if plan.suite == "spider"
        else [json.loads(line) for line in content.splitlines() if line.strip()]
    )
    return [case["id"] for case in cases]


def checkpoint(plan: ExperimentPlan) -> int:
    return prediction_prefix(Path(plan.predictions), ids(plan))


def ensure_no_latch(plan: SequencePlan) -> None:
    paths = [
        directory(plan) / "server.resource-stop.json",
        directory(plan) / "cleanup.resource-stop.json",
    ] + [Path(child.report).with_suffix(".resource-stop.json") for child in plan.benchmarks]
    for path in paths:
        if path.exists():
            reason = json.loads(path.read_text()).get("reason", "unknown resource stop")
            raise ValueError(
                f"Resource stop latched: {path}: {reason}; no automatic retry/override"
            )


def emit(output: TextIO, line: str) -> None:
    output.write(line + "\n")
    output.flush()
    print(line, flush=True)


def pump(process: subprocess.Popen[str], messages: queue.Queue[str | None]) -> None:
    if process.stdout is not None:
        for line in process.stdout:
            messages.put(line.rstrip("\n"))
    messages.put(None)


def windows_path(path: Path) -> str:
    return subprocess.check_output(["wslpath", "-w", str(path)], text=True, timeout=2).strip()


class OwnedServer:
    def __init__(self, plan: SequencePlan, output: TextIO) -> None:
        self.plan, self.output = plan, output
        self.process: subprocess.Popen[str] | None = None
        self.proxy: subprocess.Popen[str] | None = None
        self.handle: TextIO | None = None
        self.location = directory(plan)

    def heartbeat(self) -> None:
        (self.location / "server.heartbeat").touch()

    def start(self) -> int:
        child = self.plan.spider
        environment = frozen_environment(child)
        environment.update(PROFILES[self.plan.profile].ollama_environment())
        limits_path = self.location / "server.limits.json"
        atomic_json(limits_path, PROFILES[self.plan.profile].limits.model_dump(mode="json"))
        self.handle = (self.location / "server.log").open("a", encoding="utf-8", buffering=1)
        route = subprocess.check_output(
            ["ip", "route", "show", "default"], text=True, timeout=2
        ).split()
        gateway = route[route.index("via") + 1]
        with httpx.Client(timeout=0.5) as client:
            for address in (
                f"127.0.0.1:{self.plan.server_port}",
                f"{gateway}:{self.plan.backend_port}",
            ):
                try:
                    client.get(f"http://{address}/api/version")
                except httpx.HTTPError:
                    pass
                else:
                    raise ValueError("Owned backend/proxy port occupied; inspect stale jobs")
        with httpx.Client(timeout=2) as client:
            response = client.get(f"http://{gateway}:11434/api/ps")
            response.raise_for_status()
            if response.json().get("models") != []:
                raise ValueError("Existing Windows Ollama has resident models; stop them first")
        (self.location / "server.stop-request").unlink(missing_ok=True)
        self.heartbeat()
        self.process = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                windows_path(ROOT / "scripts/windows_ollama_guard.ps1"),
                "-BindAddress",
                f"{gateway}:{self.plan.backend_port}",
                "-ModelsDir",
                windows_path(Path(self.plan.models_dir)),
                "-StopFile",
                windows_path(self.location / "server.resource-stop.json"),
                "-StopRequest",
                windows_path(self.location / "server.stop-request"),
                "-Heartbeat",
                windows_path(self.location / "server.heartbeat"),
                "-Journal",
                windows_path(self.location / "server.samples.jsonl"),
                "-LimitsPath",
                windows_path(limits_path),
            ],
            cwd=ROOT,
            env=environment,
            stdout=self.handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        self.proxy = subprocess.Popen(
            [
                child.python_executable,
                "-m",
                "scripts.ollama_gateway_proxy",
                "--port",
                str(self.plan.server_port),
                "--gateway",
                gateway,
                "--backend-port",
                str(self.plan.backend_port),
            ],
            cwd=ROOT,
            stdout=self.handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        return self.process.pid

    def wait_ready(self) -> None:
        deadline = time.monotonic() + 20
        with httpx.Client(timeout=0.5) as client:
            while time.monotonic() < deadline:
                self.check()
                try:
                    response = client.get(f"http://127.0.0.1:{self.plan.server_port}/api/version")
                    response.raise_for_status()
                    emit(self.output, f"Owned guarded Windows Ollama ready: {response.json()}")
                    return
                except httpx.HTTPError:
                    time.sleep(0.2)
        raise ValueError("Owned Ollama startup timeout; inspect server.log")

    def check(self) -> None:
        ensure_no_latch(self.plan)
        self.heartbeat()
        if self.process is None or self.process.poll() is not None:
            raise ValueError("Owned Windows guardian exited; inspect server.log")
        if self.proxy is None or self.proxy.poll() is not None:
            raise ValueError("Owned loopback proxy exited; inspect server.log")

    def close(self) -> None:
        try:
            (self.location / "server.stop-request").touch()
            if self.process is not None and self.process.poll() is None:
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Heartbeat expiry is a second fail-closed path for native descendants.
                    (self.location / "server.heartbeat").unlink(missing_ok=True)
                    _stop(self.process)
                    raise ValueError(
                        "Native guardian cleanup timed out; inspect Windows jobs"
                    ) from None
            if self.process is not None and self.process.returncode:
                latch = self.location / "server.resource-stop.json"
                evidence = json.loads(latch.read_text()) if latch.exists() else {}
                if evidence.get("cleanup_complete") is not True:
                    raise ValueError("Native cleanup unverified; inspect server resource-stop/log")
        finally:
            if self.proxy is not None:
                _stop(self.proxy)
            if self.handle is not None:
                self.handle.close()


def verify_pilot(child: ExperimentPlan) -> None:
    predictions = [
        json.loads(line)
        for line in Path(child.predictions).read_text().splitlines()
        if line.strip()
    ]
    if not predictions or predictions[-1]["result"]["status"] != "SUCCEEDED":
        raise ValueError(f"{child.suite} pilot has no executable result; do not continue full run")
    journal = Path(child.report).with_suffix(".resource-stop.samples.jsonl")
    records = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    record = records[-1]
    peak = record["observed_peak"]
    if record.get("resource_stop") or record.get("cleanup_error") or record.get("samples", 0) < 2:
        raise ValueError("Pilot resource/cleanup evidence is incomplete")
    cap = record.get("limits", {}).get("maximum_gpu_clock_mhz")
    if not peak or peak.get("gpu_clock_mhz") is None or cap is None or peak["gpu_clock_mhz"] > cap:
        raise ValueError("Pilot did not verify its configured hardware clock cap")
    if peak.get("windows_available_ram_gib") is None:
        raise ValueError("Pilot Windows RAM monitoring evidence is missing")


def wait_worker_cleanup(process: subprocess.Popen[str], server: OwnedServer) -> None:
    """Keep the native owner alive while a wrapper finishes cleanup and cooldown."""
    deadline = time.monotonic() + 200
    while process.poll() is None:
        server.heartbeat()
        try:
            process.wait(timeout=min(0.2, max(0, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            if time.monotonic() >= deadline:
                _stop(process)
                return


def execute(plan: SequencePlan, max_batches: int | None, recovery: bool) -> int:
    location = directory(plan)
    location.mkdir(parents=True, exist_ok=True)
    pause_path = location / "pause-request.json"
    previous = (
        SequenceState.model_validate_json((location / "sequence-state.json").read_text())
        if (location / "sequence-state.json").exists()
        else None
    )
    ensure_no_latch(plan)
    for child in plan.benchmarks:
        frozen_environment(child)
    if (
        previous
        and previous.boot_id == boot_id()
        and any(
            process_group_alive(pid)
            for pid in (previous.worker_pid, previous.server_pid, previous.proxy_pid)
        )
    ):
        raise ValueError("Stale sequence worker/server is still alive")
    unclean = previous is not None and (
        previous.recovery_required
        or previous.boot_id != boot_id()
        or previous.phase in {"PREPARING", "PILOT", "RUNNING"}
    )
    if unclean and not recovery:
        raise ValueError("Unclean stop/reboot: resume with --recovery-pilot first")
    state = SequenceState(
        phase="PREPARING",
        boot_id=boot_id(),
        pilot_passed=previous.pilot_passed if previous else {},
        recovery_required=unclean,
    )
    requested_pause = False

    def request_pause(signum: int, frame: object) -> None:
        nonlocal requested_pause
        del signum, frame
        requested_pause = True
        atomic_json(pause_path, {"pause": True})

    handlers = {sig: signal.signal(sig, request_pause) for sig in (signal.SIGINT, signal.SIGTERM)}
    server: OwnedServer | None = None
    batches = 0
    with (location / "run.log").open("a", encoding="utf-8", buffering=1) as output:
        try:
            with workload_lease(location / "sequence.lock"):
                save(plan, state)
                server = OwnedServer(plan, output)
                state.server_pid = server.start()
                state.proxy_pid = server.proxy.pid if server.proxy else None
                save(plan, state)
                server.wait_ready()
                while True:
                    state.completed = {child.suite: checkpoint(child) for child in plan.benchmarks}
                    pending = [
                        child
                        for child in plan.benchmarks
                        if checkpoint(child) < len(ids(child)) or not Path(child.report).exists()
                    ]
                    if not pending:
                        for child in plan.benchmarks:
                            require_complete_report(Path(child.report), ids(child))
                        server.close()
                        server = None
                        state.server_pid = state.proxy_pid = None
                        ensure_no_latch(plan)
                        state.phase, state.reason = "COMPLETE", "Both reports and cleanup validated"
                        save(plan, state)
                        spider_total, olist_total = (len(ids(item)) for item in plan.benchmarks)
                        emit(
                            output,
                            f"SUCCESS FINISH ALL: Spider {spider_total}/{spider_total} "
                            f"+ Olist {olist_total}/{olist_total}",
                        )
                        return 0
                    if (
                        requested_pause
                        or pause_path.exists()
                        or (max_batches is not None and batches >= max_batches)
                        or (recovery and batches >= 1)
                    ):
                        state.phase = "PAUSED"
                        state.reason = (
                            "Checkpoint and cooldown complete; operator/batch/pilot boundary"
                        )
                        save(plan, state)
                        emit(output, f"PAUSED BOTH: {state.completed}; pilots={state.pilot_passed}")
                        return 0
                    # First perform one independent case for each workload; then finish in order.
                    child = next(
                        (item for item in pending if not state.pilot_passed.get(item.suite)),
                        pending[0],
                    )
                    state.active_benchmark = child.suite
                    state.phase = "PILOT" if not state.pilot_passed.get(child.suite) else "RUNNING"
                    command = wrapper_command(child, 1, recovery and batches == 0)
                    emit(
                        output,
                        f"START {state.phase}: {child.suite} {checkpoint(child)}/{len(ids(child))}",
                    )
                    completed_before = checkpoint(child)
                    process = subprocess.Popen(
                        command,
                        cwd=ROOT,
                        env=frozen_environment(child),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        start_new_session=True,
                    )
                    state.worker_pid = process.pid
                    save(plan, state)
                    messages: queue.Queue[str | None] = queue.Queue(maxsize=256)
                    reader = threading.Thread(target=pump, args=(process, messages), daemon=True)
                    reader.start()
                    ended = False
                    try:
                        while not ended or process.poll() is None:
                            server.check()
                            if requested_pause or pause_path.exists():
                                atomic_json(
                                    Path(child.report).with_suffix(".pause-request.json"),
                                    {"pause": True},
                                )
                            try:
                                line = messages.get(timeout=0.2)
                                if line is None:
                                    ended = True
                                else:
                                    emit(output, f"[{child.suite}] {line}")
                            except queue.Empty:
                                pass
                        code = process.wait()
                        if code:
                            raise ValueError(
                                f"{child.suite} guarded wrapper exited {code}; no auto-retry"
                            )
                    finally:
                        if process.poll() is None:
                            process.send_signal(signal.SIGINT)  # Graceful boundary pause.
                            wait_worker_cleanup(process, server)
                        if process.stdout is not None:
                            process.stdout.close()
                    state.worker_pid = None
                    suite_state = SuiteState.model_validate_json(
                        Path(child.report).with_suffix(".suite-state.json").read_text()
                    )
                    if suite_state.phase not in {"PAUSED", "COMPLETE"}:
                        raise ValueError(f"{child.suite} did not reach a clean checkpoint boundary")
                    if checkpoint(child) == completed_before and (
                        requested_pause or pause_path.exists()
                    ):
                        state.phase, state.reason = "PAUSED", "Paused before another case completed"
                        save(plan, state)
                        return 0
                    if not state.pilot_passed.get(child.suite) or (recovery and batches == 0):
                        verify_pilot(child)
                        state.pilot_passed[child.suite] = True
                        emit(
                            output,
                            f"PILOT VERIFIED: {child.suite}; clock cap and resources recorded",
                        )
                    batches += 1
                    state.recovery_required = False
                    state.completed[child.suite] = checkpoint(child)
                    save(plan, state)
                    # Only operator pause markers need clearing on resume.
        except (ValueError, OSError, subprocess.SubprocessError, RuntimeError) as exc:
            latched = any(
                Path(child.report).with_suffix(".resource-stop.json").exists()
                for child in plan.benchmarks
            )
            state.phase = (
                "RESOURCE_STOP"
                if latched or (location / "server.resource-stop.json").exists()
                else "FAILED"
            )
            state.reason = str(exc)
            if not process_group_alive(state.worker_pid):
                state.worker_pid = None
            state.completed = {child.suite: checkpoint(child) for child in plan.benchmarks}
            save(plan, state)
            emit(output, f"STOP BOTH: {state.reason}; checkpoints={state.completed}")
            return 1
        finally:
            cleanup_failed = False
            if server is not None:
                try:
                    server.close()
                    state.server_pid = state.proxy_pid = None
                except (ValueError, OSError, subprocess.SubprocessError) as exc:
                    cleanup_failed = True
                    state.phase, state.reason = "RESOURCE_STOP", f"Cleanup failed: {exc}"
                    atomic_json(location / "cleanup.resource-stop.json", {"reason": state.reason})
                    emit(output, state.reason)
                save(plan, state)
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
            if cleanup_failed:
                raise RuntimeError(state.reason)


def launch(plan: SequencePlan, max_batches: int | None, recovery: bool) -> None:
    ensure_no_latch(plan)
    frozen_environment(plan.spider)
    command = [
        plan.spider.python_executable,
        "-m",
        "scripts.tmux_benchmarks",
        "execute",
        "--plan",
        str(directory(plan) / "sequence-plan.json"),
    ]
    if max_batches is not None:
        command.extend(["--max-batches", str(max_batches)])
    if recovery:
        command.append("--recovery-pilot")
    target = f"{plan.name}:0.0"
    shell_command = "exec " + shlex.join(command)
    if session_exists(plan.name):
        if (
            tmux("display-message", "-p", "-t", target, "#{pane_dead}", capture=True).stdout.strip()
            != "1"
        ):
            print(f"Sequence already active: tmux attach -t {plan.name}")
            return
        (directory(plan) / "pause-request.json").unlink(missing_ok=True)
        for child in plan.benchmarks:
            Path(child.report).with_suffix(".pause-request.json").unlink(missing_ok=True)
        tmux("respawn-pane", "-t", target, "-c", str(ROOT), shell_command)
    else:
        (directory(plan) / "pause-request.json").unlink(missing_ok=True)
        for child in plan.benchmarks:
            Path(child.report).with_suffix(".pause-request.json").unlink(missing_ok=True)
        tmux("new-session", "-d", "-s", plan.name, "-c", str(ROOT))
        tmux("set-option", "-w", "-t", target, "remain-on-exit", "on")
        tmux("send-keys", "-t", target, "-l", shell_command)
        tmux("send-keys", "-t", target, "Enter")
    print(f"Started both benchmarks: tmux attach -t {plan.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser("run")
    run.add_argument("--name", required=True)
    run.add_argument("--variant", choices=VARIANTS, default="obligation-cpu")
    run.add_argument(
        "--profile",
        choices=[ProfileName.CLOCK_CAPPED.value, ProfileName.QWEN_FULL_GPU.value],
        default=ProfileName.QWEN_FULL_GPU.value,
    )
    run.add_argument("--models-dir", type=Path, required=True)
    run.add_argument("--server-port", type=int, default=11435)
    run.add_argument("--backend-port", type=int, default=11436)
    run.add_argument("--max-batches", type=int)
    run.add_argument("--manifest", type=Path, default=ROOT / "evals/configs/spider-laptop-200.json")
    run.add_argument("--cases", type=Path, default=ROOT / "evals/configs/olist-acceptance-60.jsonl")
    for action in ("resume", "pause", "status", "attach"):
        child_parser = commands.add_parser(action)
        child_parser.add_argument("--name", required=True)
        if action == "resume":
            child_parser.add_argument("--max-batches", type=int)
            child_parser.add_argument("--recovery-pilot", action="store_true")
    worker = commands.add_parser("execute")
    worker.add_argument("--plan", type=Path, required=True)
    worker.add_argument("--max-batches", type=int)
    worker.add_argument("--recovery-pilot", action="store_true")
    args = parser.parse_args()
    if getattr(args, "max_batches", None) is not None and args.max_batches < 1:
        parser.error("max-batches must be positive")
    if args.action == "run":
        target = plan_path(args.name).parent / "sequence-plan.json"
        if target.exists() or session_exists(args.name):
            raise SystemExit("Sequence already exists; use resume or a fresh name")
        if not (args.models_dir / "manifests").is_dir():
            raise SystemExit("Existing Ollama models directory is missing")
        if args.server_port == args.backend_port:
            raise SystemExit("Backend and proxy ports must differ")
        children = []
        for kind in ("spider", "olist"):
            namespace = argparse.Namespace(
                name=f"{args.name}-{kind}",
                suite=kind,
                variant=args.variant,
                profile=args.profile,
                manifest=args.manifest,
                cases=args.cases,
                predictions=ROOT / f"evals/predictions/{args.name}-{kind}.jsonl",
                report=ROOT / f"evals/reports/{args.name}-{kind}.json",
                allow_dirty_source=True,
            )
            child = create_plan(
                namespace,
                settings_overrides={
                    "OLLAMA_BASE_URL": f"http://127.0.0.1:{args.server_port}",
                    "TEXT2SQL_MONITOR_WINDOWS_HOST": "true",
                    "TEXT2SQL_OLLAMA_NUM_THREAD": "8",
                },
            )
            if Path(child.predictions).exists() or Path(child.report).exists():
                raise SystemExit("New sequence requires unused prediction/report paths")
            children.append(child)
        plan = SequencePlan(
            name=args.name,
            spider=children[0],
            olist=children[1],
            models_dir=str(args.models_dir.resolve()),
            profile=ProfileName(args.profile),
            server_port=args.server_port,
            backend_port=args.backend_port,
        )
        atomic_json(target, plan.model_dump(mode="json"))
        launch(plan, args.max_batches, False)
    else:
        target = (
            args.plan
            if args.action == "execute"
            else plan_path(args.name).parent / "sequence-plan.json"
        )
        plan = SequencePlan.model_validate_json(target.read_text())
        if args.action == "execute":
            raise SystemExit(execute(plan, args.max_batches, args.recovery_pilot))
        if args.action == "resume":
            launch(plan, args.max_batches, args.recovery_pilot)
        elif args.action == "pause":
            atomic_json(directory(plan) / "pause-request.json", {"pause": True})
            print("Pause requested for both benchmarks; wait for checkpoint, unload and cooldown")
        elif args.action == "attach":
            tmux("attach-session", "-t", f"={plan.name}")
        else:
            print((directory(plan) / "sequence-state.json").read_text())


if __name__ == "__main__":
    main()
