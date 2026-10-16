"""Run one local CLI request under continuous conservative monitoring (not a suite)."""

import argparse
import os
from pathlib import Path

from agentic_text2sql.hardware import PROFILES, ProfileName
from agentic_text2sql.resource_guard import guarded_process
from agentic_text2sql.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stop-file", type=Path, default=Path("data/artifacts/local.resource-stop.json")
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    parser.add_argument(
        "--profile", choices=[p.value for p in ProfileName], default=ProfileName.ACCEPTANCE
    )
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise SystemExit("Provide one local command after --")
    profile = PROFILES[ProfileName(args.profile)]
    guarded_process(
        command,
        cwd=Path(__file__).resolve().parents[1],
        environment={
            **os.environ,
            **profile.ollama_environment(),
            "TEXT2SQL_RESOURCE_PROFILE": profile.model_dump_json(),
        },
        base_url=Settings().ollama_base_url,
        stop_path=args.stop_file,
        limits=profile.limits,
        cooldown_seconds=60,
    )


if __name__ == "__main__":
    main()
