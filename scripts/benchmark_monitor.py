"""Read-only benchmark dashboard; stays visible after a worker stops, never retries it."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from pydantic import ValidationError

from agentic_text2sql_eval.suite_control import boot_id, process_alive, require_complete_report
from scripts.tmux_benchmarks import SequencePlan, SequenceState, ids


def tail(path: Path, *, lines: int = 16, maximum_bytes: int = 16384) -> str:
    try:
        with path.open("rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - maximum_bytes))
            return "\n".join(stream.read().decode("utf-8", errors="replace").splitlines()[-lines:])
    except OSError as exc:
        return f"Log unavailable: {type(exc).__name__}"


def render(plan: SequencePlan, location: Path, *, width: int = 100, height: int = 30) -> str:
    """State/latches are authoritative; a live monitor is not proof of a live job."""
    phase, reason = "STARTING", "Waiting for worker state"
    counts: dict[str, int] = {}
    state: SequenceState | None = None
    state_path = location / "sequence-state.json"
    if state_path.exists():
        try:
            state = SequenceState.model_validate_json(state_path.read_text())
            phase, reason, counts = state.phase, state.reason or "", state.completed
            if state.boot_id != boot_id() and phase in {"PREPARING", "PILOT", "RUNNING"}:
                phase, reason = "RECOVERY_REQUIRED", "Host rebooted; stale worker state"
            elif phase in {"PILOT", "RUNNING"} and not process_alive(state.server_pid):
                phase, reason = "UNKNOWN", "Server owner is absent; do not infer progress"
            elif phase == "PAUSED" and any(
                process_alive(pid) for pid in (state.worker_pid, state.server_pid, state.proxy_pid)
            ):
                phase, reason = "PAUSING", "Waiting for owned worker/server cleanup"
            elif phase == "COMPLETE":
                for child in plan.benchmarks:
                    require_complete_report(Path(child.report), ids(child))
        except (OSError, ValueError, ValidationError) as exc:
            phase, reason = "UNKNOWN", f"State unavailable: {type(exc).__name__}"
    latches = [location / "server.resource-stop.json", location / "cleanup.resource-stop.json"]
    latches += [Path(child.report).with_suffix(".resource-stop.json") for child in plan.benchmarks]
    for latch in latches:
        if not latch.exists():
            continue
        phase = "RESOURCE_STOP"
        try:
            reason = str(json.loads(latch.read_text()).get("reason", "Resource stop latched"))
        except (OSError, ValueError, AttributeError):
            reason = "Resource stop latch exists but is unreadable"
        reason += f"\nEvidence: {latch}"
        break
    lines = [
        f"{plan.name} | {phase}",
        f"Profile: {plan.profile}",
        "Read-only monitor. No automatic restart, retry or latch removal.",
    ]
    for child in plan.benchmarks:
        try:
            total = len(ids(child))
            lines.append(f"{child.suite}: {counts.get(child.suite, 0)}/{total}")
        except (OSError, ValueError, KeyError, TypeError):
            lines.append(f"{child.suite}: manifest unavailable")
    if reason:
        lines.append(f"Reason: {reason}")
    if phase == "RESOURCE_STOP":
        lines.append("WORKLOAD STOPPED. Preserve evidence; hardware/resource remediation required.")
    if state:
        lines.append(f"Worker PID: {state.worker_pid} | Server owner PID: {state.server_pid}")
    lines.extend(
        [
            "Ctrl+b then d: detach. Ctrl+b then 0: raw worker log.",
            f"Pause: python -m scripts.tmux_benchmarks pause --name {plan.name}",
            "--- Recent worker output (full log in window 0) ---",
        ]
    )
    lines = "\n".join(lines).splitlines()
    # Wrapped tracebacks/large JSON must not scroll the phase and checkpoint off screen.
    line_budget = max(0, height - len(lines) - 1)
    lines.extend(
        tail(location / "run.log", lines=min(8, line_budget)).splitlines() if line_budget else []
    )
    return "\n".join(
        line if len(line) <= width else line[: max(1, width - 1)] + "…"
        for line in lines[: max(1, height - 1)]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    plan = SequencePlan.model_validate_json(args.plan.read_text())
    try:
        while True:
            try:
                size = shutil.get_terminal_size((100, 30))
                display = render(plan, args.plan.parent, width=size.columns, height=size.lines)
            except (
                Exception
            ) as exc:  # Monitoring errors must be visible, never reported as healthy.
                display = f"{plan.name} | UNKNOWN\nMonitor error: {type(exc).__name__}: {exc}"
            if sys.stdout.isatty() and not args.once:
                print("\033[2J\033[H", end="")
            print(display, flush=True)
            if args.once:
                return
            time.sleep(2)
    except KeyboardInterrupt:
        print("Monitor closed. Workload state was not changed.", flush=True)


if __name__ == "__main__":
    main()
