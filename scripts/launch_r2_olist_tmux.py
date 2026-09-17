"""Launch the guarded R2 server and benchmark in a persistent tmux session."""

from __future__ import annotations

import argparse
import re
import shlex
import socket
import subprocess
from pathlib import Path

from agentic_text2sql.hardware import PROFILES, ProfileName, sample_resources, unsafe_reason

_SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")


def _shell(command: list[str]) -> str:
    return shlex.join(command)


def build_window_shells(
    root: Path,
    *,
    evaluation_id: str,
    session: str,
    models_dir: Path | None,
    skip_check: bool,
    recovery_source_evaluation_id: str | None = None,
) -> tuple[str, str]:
    reports = root / "evals" / "reports"
    server_log = reports / f"{evaluation_id}.server.log"
    benchmark_log = reports / f"{evaluation_id}.benchmark.log"
    server = [
        "uv",
        "run",
        "python",
        "scripts/serve_ollama_guarded.py",
        "--profile",
        "olist-paper1-ultrasafe",
        "--sample-seconds",
        "0.5",
    ]
    if models_dir is not None:
        server.extend(("--models-dir", str(models_dir)))
    benchmark_script = (
        "scripts/run_r2_olist_recovery.py"
        if recovery_source_evaluation_id is not None
        else "scripts/run_r2_olist_research.py"
    )
    benchmark = [
        "uv",
        "run",
        "python",
        benchmark_script,
        "--evaluation-id",
        evaluation_id,
    ]
    if recovery_source_evaluation_id is not None:
        benchmark.extend(("--source-evaluation-id", recovery_source_evaluation_id))
    if skip_check:
        benchmark.append("--skip-check")

    server_shell = (
        "set -o pipefail; "
        f"{_shell(server)} 2>&1 | tee -a {shlex.quote(str(server_log))}; "
        "status=${PIPESTATUS[0]}; "
        f'echo "GUARDED_SERVER_EXIT=$status" | tee -a {shlex.quote(str(server_log))}; '
        "exit $status"
    )
    server_target = f"{session}:server"
    benchmark_shell = (
        "set -o pipefail; "
        f"cleanup() {{ tmux send-keys -t {shlex.quote(server_target)} C-c 2>/dev/null || true; }}; "
        "trap cleanup EXIT; ready=0; "
        "for attempt in $(seq 1 120); do "
        "if curl -fsS --max-time 1 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; "
        "then ready=1; break; fi; sleep 1; done; "
        f'if [ "$ready" -ne 1 ]; then echo "GUARDED_SERVER_NOT_READY" | tee -a '
        f"{shlex.quote(str(benchmark_log))}; exit 70; fi; "
        f"{_shell(benchmark)} 2>&1 | tee -a {shlex.quote(str(benchmark_log))}; "
        "status=${PIPESTATUS[0]}; "
        f'echo "R2_BENCHMARK_EXIT=$status" | tee -a {shlex.quote(str(benchmark_log))}; '
        "exit $status"
    )
    return server_shell, benchmark_shell


def port_is_open(host: str = "127.0.0.1", port: int = 11434) -> bool:
    with socket.socket() as connection:
        connection.settimeout(0.25)
        return connection.connect_ex((host, port)) == 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation-id", required=True)
    parser.add_argument("--session")
    parser.add_argument("--models-dir", type=Path)
    parser.add_argument("--skip-check", action="store_true")
    parser.add_argument(
        "--recovery-source-evaluation-id",
        help="Run sparse adaptive recovery from this prior incomplete evaluation.",
    )
    parser.add_argument(
        "--hard-cap-confirmed",
        action="store_true",
        help="Assert that the Administrator 300-600 MHz lock command reported success.",
    )
    args = parser.parse_args()
    if _SAFE_NAME.fullmatch(args.evaluation_id) is None:
        raise SystemExit("evaluation-id must be 3-80 lowercase safe characters")
    if (
        args.recovery_source_evaluation_id is not None
        and _SAFE_NAME.fullmatch(args.recovery_source_evaluation_id) is None
    ):
        raise SystemExit("recovery source evaluation ID must be 3-80 lowercase safe characters")
    session = args.session or f"olist-r2-{args.evaluation_id}"
    if _SAFE_NAME.fullmatch(session) is None:
        raise SystemExit("session must be 3-80 lowercase safe characters")
    if not args.hard_cap_confirmed:
        raise SystemExit(
            "HARD_CAP_CONFIRMATION_REQUIRED: apply Administrator nvidia-smi -lgc 300,600, "
            "then pass --hard-cap-confirmed; the one-case guarded pilot will verify it under load"
        )

    root = Path(__file__).resolve().parents[1]
    if port_is_open():
        raise SystemExit(
            "OLLAMA_PORT_IN_USE: stop the unverified server before launching the dual-guard session"
        )
    existing = subprocess.run(
        ["tmux", "has-session", "-t", session],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if existing.returncode == 0:
        raise SystemExit(f"TMUX_SESSION_EXISTS: attach with: tmux attach -t {session}")

    profile = PROFILES[ProfileName.OLIST_PAPER1]
    try:
        sample = sample_resources()
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise SystemExit(
            f"RESOURCE_GUARD_REFUSED_START: monitor failure {type(exc).__name__}"
        ) from None
    if reason := unsafe_reason(sample, profile.limits):
        raise SystemExit(f"RESOURCE_GUARD_REFUSED_START: {reason}")

    models_dir = args.models_dir.resolve() if args.models_dir is not None else None
    if models_dir is not None and not models_dir.is_dir():
        raise SystemExit(f"models-dir does not exist: {models_dir}")
    (root / "evals" / "reports").mkdir(parents=True, exist_ok=True)
    server_shell, benchmark_shell = build_window_shells(
        root,
        evaluation_id=args.evaluation_id,
        session=session,
        models_dir=models_dir,
        skip_check=args.skip_check,
        recovery_source_evaluation_id=args.recovery_source_evaluation_id,
    )
    subprocess.run(
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            session,
            "-n",
            "server",
            "-c",
            str(root),
            "bash",
            "-lc",
            server_shell,
        ],
        check=True,
    )
    subprocess.run(
        ["tmux", "set-window-option", "-t", f"{session}:server", "remain-on-exit", "on"],
        check=True,
    )
    subprocess.run(
        [
            "tmux",
            "new-window",
            "-d",
            "-t",
            session,
            "-n",
            "benchmark",
            "-c",
            str(root),
            "bash",
            "-lc",
            benchmark_shell,
        ],
        check=True,
    )
    subprocess.run(
        ["tmux", "set-window-option", "-t", f"{session}:benchmark", "remain-on-exit", "on"],
        check=True,
    )
    subprocess.run(["tmux", "select-window", "-t", f"{session}:benchmark"], check=True)
    print(f"TMUX_STARTED: {session}")
    print(f"attach: tmux attach -t {session}")
    print(f"benchmark log: evals/reports/{args.evaluation_id}.benchmark.log")
    print(f"server log: evals/reports/{args.evaluation_id}.server.log")
    print(f"pipeline status: evals/reports/{args.evaluation_id}.pipeline-status.json")


if __name__ == "__main__":
    main()
