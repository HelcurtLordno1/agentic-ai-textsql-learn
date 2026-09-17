"""Launch a guarded one-case Spider pilot, then continue the pinned 200-case run."""

from __future__ import annotations

import argparse
import re
import shlex
import socket
import subprocess
from pathlib import Path

from agentic_text2sql.hardware import PROFILES, ProfileName, sample_resources, unsafe_reason
from agentic_text2sql_eval.spider_release import load_release_cases

_SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")


def port_is_open(host: str = "127.0.0.1", port: int = 11434) -> bool:
    with socket.socket() as connection:
        connection.settimeout(0.25)
        return connection.connect_ex((host, port)) == 0


def build_window_shells(
    root: Path,
    *,
    evaluation_id: str,
    session: str,
    models_dir: Path,
    stop_record: Path | None = None,
) -> tuple[str, str]:
    reports = root / "evals/reports"
    predictions = root / "evals/predictions" / f"{evaluation_id}.jsonl"
    report = reports / f"{evaluation_id}.json"
    progress = reports / f"{evaluation_id}.progress.json"
    stop_record = stop_record or reports / f"{evaluation_id}.resource-stop.json"
    manifest = root / "evals/configs/spider-laptop-200.json"
    server_log = reports / f"{evaluation_id}.server.log"
    benchmark_log = reports / f"{evaluation_id}.benchmark.log"
    server_command = [
        "uv",
        "run",
        "python",
        "scripts/serve_ollama_guarded.py",
        "--profile",
        ProfileName.SPIDER_PAPER2.value,
        "--sample-seconds",
        "0.5",
        "--models-dir",
        str(models_dir),
        "--stop-record",
        str(stop_record),
    ]
    benchmark_command = [
        "uv",
        "run",
        "python",
        "scripts/run_guarded_spider.py",
        "--profile",
        ProfileName.SPIDER_PAPER2.value,
        "--batch-size",
        "1",
        "--cooldown-seconds",
        "60",
        "--sample-seconds",
        "0.5",
        "--evaluation-id",
        evaluation_id,
        "--predictions",
        str(predictions),
        "--report",
        str(report),
        "--manifest",
        str(manifest),
        "--progress-report",
        str(progress),
        "--stop-record",
        str(stop_record),
    ]
    server_shell = (
        "set -o pipefail; "
        f"{shlex.join(server_command)} 2>&1 | tee -a {shlex.quote(str(server_log))}; "
        "status=${PIPESTATUS[0]}; "
        f'echo "GUARDED_SERVER_EXIT=$status" | tee -a {shlex.quote(str(server_log))}; '
        "exit $status"
    )
    server_target = shlex.quote(f"{session}:server")
    pilot = shlex.join([*benchmark_command, "--phase", "pilot", "--max-batches", "1"])
    continuation = shlex.join([*benchmark_command, "--phase", "inference"])
    benchmark_shell = (
        "set -o pipefail; "
        f"cleanup() {{ tmux send-keys -t {server_target} C-c 2>/dev/null || true; }}; "
        "trap cleanup EXIT; ready=0; "
        "for attempt in $(seq 1 120); do "
        "if curl -fsS --max-time 1 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; "
        "then ready=1; break; fi; sleep 1; done; "
        f'if [ "$ready" -ne 1 ]; then echo "GUARDED_SERVER_NOT_READY" | tee -a '
        f"{shlex.quote(str(benchmark_log))}; exit 70; fi; "
        f"{pilot} 2>&1 | tee -a {shlex.quote(str(benchmark_log))}; "
        "status=${PIPESTATUS[0]}; "
        f'if [ "$status" -ne 0 ]; then echo "SPIDER_PILOT_EXIT=$status" | tee -a '
        f"{shlex.quote(str(benchmark_log))}; exit $status; fi; "
        f"{continuation} 2>&1 | tee -a {shlex.quote(str(benchmark_log))}; "
        "status=${PIPESTATUS[0]}; "
        f'echo "SPIDER_BENCHMARK_EXIT=$status" | tee -a {shlex.quote(str(benchmark_log))}; '
        "exit $status"
    )
    return server_shell, benchmark_shell


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation-id", required=True)
    parser.add_argument("--session")
    parser.add_argument("--models-dir", type=Path, required=True)
    parser.add_argument("--hard-cap-confirmed", action="store_true")
    parser.add_argument(
        "--acknowledge-clock-stop",
        action="store_true",
        help="Resume a reviewed clock-only stop with a new session-scoped stop record.",
    )
    args = parser.parse_args()
    if _SAFE_NAME.fullmatch(args.evaluation_id) is None:
        raise SystemExit("evaluation-id must be 3-80 lowercase safe characters")
    session = args.session or f"spider-r2-{args.evaluation_id}"
    if _SAFE_NAME.fullmatch(session) is None:
        raise SystemExit("session must be 3-80 lowercase safe characters")
    if not args.hard_cap_confirmed:
        raise SystemExit(
            "HARD_CAP_CONFIRMATION_REQUIRED: verify Administrator nvidia-smi -lgc 900,1200; "
            "the guarded one-case pilot will also check the clock under load"
        )
    root = Path(__file__).resolve().parents[1]
    prior_stop = root / "evals/reports" / f"{args.evaluation_id}.resource-stop.json"
    later_stops = sorted(
        (root / "evals/reports").glob(f"{args.evaluation_id}.*.resource-stop.json")
    )
    if later_stops:
        raise SystemExit(f"RESOURCE_STOP_LOCKED: most recent session incident {later_stops[-1]}")
    if prior_stop.is_file() and not args.acknowledge_clock_stop:
        raise SystemExit(f"RESOURCE_STOP_LOCKED: {prior_stop}")
    if args.acknowledge_clock_stop:
        from scripts.migrate_spider_clock_guard import reviewed_clock_stop

        reviewed_clock_stop(prior_stop, PROFILES[ProfileName.SPIDER_PAPER2].limits)
        provenance = root / "evals/predictions" / f"{args.evaluation_id}.provenance.json"
        from scripts.migrate_spider_clock_guard import migration_is_current

        if not migration_is_current(provenance, root, prior_stop):
            raise SystemExit("SPIDER_GUARD_MIGRATION_REQUIRED: run migrate_spider_clock_guard.py")
        stop_record = root / "evals/reports" / f"{args.evaluation_id}.{session}.resource-stop.json"
    else:
        stop_record = prior_stop
    if stop_record.is_file():
        raise SystemExit(f"RESOURCE_STOP_LOCKED: {stop_record}")
    if port_is_open():
        raise SystemExit("OLLAMA_PORT_IN_USE: stop the unverified server before launching")
    if (
        subprocess.run(
            ["tmux", "has-session", "-t", session],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    ):
        raise SystemExit(f"TMUX_SESSION_EXISTS: tmux attach -t {session}")
    models_dir = args.models_dir.resolve()
    if not models_dir.is_dir():
        raise SystemExit(f"models-dir does not exist: {models_dir}")
    manifest = root / "evals/configs/spider-laptop-200.json"
    release, cases = load_release_cases(root / "data/raw/spider/spider_data", manifest)
    if release.benchmark_profile != "laptop-stratified" or len(cases) != 200:
        raise SystemExit("SPIDER_MANIFEST_MISMATCH: expected pinned stratified 200 cases")
    try:
        current = sample_resources()
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise SystemExit(f"RESOURCE_GUARD_REFUSED_START: {type(exc).__name__}") from None
    if reason := unsafe_reason(current, PROFILES[ProfileName.SPIDER_PAPER2].limits):
        raise SystemExit(f"RESOURCE_GUARD_REFUSED_START: {reason}")
    (root / "evals/reports").mkdir(parents=True, exist_ok=True)
    server_shell, benchmark_shell = build_window_shells(
        root,
        evaluation_id=args.evaluation_id,
        session=session,
        models_dir=models_dir,
        stop_record=stop_record,
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
    print(f"progress: evals/reports/{args.evaluation_id}.progress.json")
    print(f"benchmark log: evals/reports/{args.evaluation_id}.benchmark.log")


if __name__ == "__main__":
    main()
