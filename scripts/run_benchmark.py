"""Run a pinned Spider release manifest; full dev remains an optional profile."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from agentic_text2sql.contracts.sql import DirectStatus
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer6_application.service_factory import RuntimeBundle
from agentic_text2sql.settings import Settings
from agentic_text2sql_eval.inference_runner import SmokePrediction
from agentic_text2sql_eval.spider_release import (
    create_release_manifest,
    evaluate_spider_release,
    load_release_cases,
)


def checkpoint(path: Path, predictions: list[SmokePrediction]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        "\n".join(item.model_dump_json() for item in predictions) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def checkpoint_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def git_provenance(root: Path) -> dict[str, object]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, timeout=5
        ).strip()
        tracked_status = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=root,
            text=True,
            timeout=5,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return {"git_commit": "unknown", "tracked_worktree_clean": False}
    return {"git_commit": commit, "tracked_worktree_clean": not tracked_status}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--create-manifest", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--correction", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-new-cases", type=int)
    args = parser.parse_args()

    settings = Settings()
    root = settings.project_root
    spider_root = root / "data/raw/spider/spider_data"
    manifest_path = args.manifest or root / "evals/configs/spider-laptop-200.json"
    predictions_path = args.predictions or root / "evals/predictions/spider-p6-200.jsonl"
    provenance_path = predictions_path.with_suffix(".provenance.json")
    report_path = args.report or root / "evals/reports/spider-p6-200.json"
    if args.create_manifest:
        manifest_path = args.manifest or root / "evals/configs/spider-release-1034.json"
        manifest = create_release_manifest(spider_root)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "manifest": str(manifest_path),
                    "case_count": manifest.case_count,
                    "database_count": manifest.database_count,
                    "dev_sha256": manifest.dev_sha256,
                },
                indent=2,
            )
        )
        return

    manifest, cases = load_release_cases(spider_root, manifest_path)
    predictions: list[SmokePrediction] = []
    if args.resume and predictions_path.is_file():
        predictions = [
            SmokePrediction.model_validate_json(line)
            for line in predictions_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    expected_prefix = [case.id for case in cases[: len(predictions)]]
    if [prediction.case_id for prediction in predictions] != expected_prefix:
        raise SystemExit("persisted Spider predictions are not a release-manifest prefix")
    revision = git_provenance(root)
    if revision["git_commit"] == "unknown" or not revision["tracked_worktree_clean"]:
        raise SystemExit("release inference requires a known commit and clean tracked worktree")
    run_config = {
        "model": settings.ollama_model,
        "num_gpu": settings.ollama_num_gpu,
        "seed": settings.ollama_seed,
        "correction_enabled": args.correction,
    }
    if provenance_path.is_file():
        run_provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        if run_provenance.get("git_commit") != revision["git_commit"]:
            raise SystemExit("persisted predictions belong to a different Git commit")
        if run_provenance.get("run_config") != run_config:
            raise SystemExit("persisted predictions belong to a different runtime configuration")
    else:
        run_provenance = {
            **revision,
            "experiment_id": "spider-dev-qwen3-14b-hybrid-p6-v1",
            "evaluator_version": "spider_release_v1",
            "oracle_evidence_used": False,
            "run_config": run_config,
            "database_runtime": {},
        }
    remaining = cases[len(predictions) :]
    if args.max_new_cases is not None:
        if args.max_new_cases < 1:
            raise SystemExit("max-new-cases must be positive")
        remaining = remaining[: args.max_new_cases]

    introspector = SQLiteIntrospector()
    database_provenance = run_provenance["database_runtime"]
    if not isinstance(database_provenance, dict):
        raise SystemExit("persisted provenance has invalid database_runtime")
    cursor = 0
    while cursor < len(remaining):
        db_id = remaining[cursor].db_id
        end = cursor
        while end < len(remaining) and remaining[end].db_id == db_id:
            end += 1
        database = spider_root / "database" / db_id / f"{db_id}.sqlite"
        catalog = introspector.inspect(database, db_id)
        with RuntimeBundle(settings, catalog, correction_enabled=args.correction) as runtime:
            database_provenance[db_id] = runtime.provenance
            checkpoint_json(provenance_path, run_provenance)
            for case in remaining[cursor:end]:
                prediction = SmokePrediction(
                    case_id=case.id,
                    result=runtime.run(case.question, database, catalog),
                )
                if prediction.result.status is DirectStatus.MODEL_ERROR and any(
                    marker in (prediction.result.safe_message or "")
                    for marker in ("ReadTimeout", "ProviderUnavailable", "request failed")
                ):
                    raise SystemExit(
                        f"infrastructure stop before checkpoint at {case.id}: "
                        f"{prediction.result.safe_message}"
                    )
                predictions.append(prediction)
                checkpoint(predictions_path, predictions)
                print(
                    f"inference {len(predictions)}/{len(cases)} {case.id} "
                    f"{case.db_id}: {prediction.result.status.value}",
                    flush=True,
                )
        cursor = end

    if len(predictions) != len(cases):
        print(
            json.dumps(
                {
                    "status": "checkpointed",
                    "completed": len(predictions),
                    "total": len(cases),
                }
            )
        )
        return
    expected_databases = {case.db_id for case in cases}
    if set(database_provenance) != expected_databases:
        raise SystemExit("release provenance is incomplete for the selected databases")
    report = evaluate_spider_release(
        spider_root=spider_root,
        manifest=manifest,
        cases=cases,
        predictions=predictions,
        report_path=report_path,
        provenance=run_provenance,
    )
    print(json.dumps({key: value for key, value in report.items() if key != "details"}, indent=2))


if __name__ == "__main__":
    main()
