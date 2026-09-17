"""Run a pinned Spider release manifest; full dev remains an optional profile."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from agentic_text2sql.contracts.sql import DirectStatus
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer6_application.service_factory import RuntimeBundle
from agentic_text2sql.settings import Settings
from agentic_text2sql_eval.inference_runner import SmokePrediction
from agentic_text2sql_eval.spider_release import (
    create_release_manifest,
    evaluate_spider_release,
    load_release_cases,
    sha256_file,
)

_EVALUATION_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")


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


def run_configuration(
    settings: Settings, *, correction_enabled: bool, profile: str
) -> dict[str, Any]:
    """Freeze every setting that can affect inference across an interrupted run."""
    return {
        "model": settings.ollama_model,
        "num_gpu": settings.ollama_num_gpu,
        "seed": settings.ollama_seed,
        "correction_enabled": correction_enabled,
        "planning_mode": settings.planning_mode,
        "candidate_mode": settings.candidate_mode,
        "certified_proof_kinds": sorted(settings.parsed_certified_proof_kinds),
        "retrieval_mode": settings.retrieval_mode,
        "max_output_tokens": settings.ollama_max_output_tokens,
        "request_timeout_seconds": settings.request_timeout_seconds,
        "run_deadline_seconds": settings.run_deadline_seconds,
        "candidate_total_deadline_seconds": settings.candidate_total_deadline_seconds,
        "candidate_minimum_challenger_seconds": settings.candidate_minimum_challenger_seconds,
        "resource_profile": profile,
    }


def verify_resume_provenance(
    payload: dict[str, Any],
    *,
    revision: dict[str, object],
    evaluation_id: str,
    manifest_sha256: str,
    index_pointer_sha256: dict[str, str],
    run_config: dict[str, Any],
) -> None:
    """Never mix predictions from another source, manifest, index or runtime mode."""
    expected = {
        "git_commit": revision["git_commit"],
        "experiment_id": evaluation_id,
        "manifest_sha256": manifest_sha256,
        "index_pointer_sha256": index_pointer_sha256,
        "run_config": run_config,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise SystemExit(f"SPIDER_RESUME_MISMATCH: {key}")
    if not isinstance(payload.get("database_runtime"), dict):
        raise SystemExit("SPIDER_RESUME_MISMATCH: database_runtime")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--create-manifest", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--correction", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-new-cases", type=int)
    parser.add_argument("--evaluation-id")
    parser.add_argument("--inference-only", action="store_true")
    parser.add_argument("--evaluate-only", action="store_true")
    args = parser.parse_args()
    if args.inference_only and args.evaluate_only:
        raise SystemExit("inference-only and evaluate-only are mutually exclusive")

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
    evaluation_id = args.evaluation_id or (
        "spider-dev-stratified-200-p6-v1"
        if manifest.benchmark_profile == "laptop-stratified"
        else "spider-dev-1034-p6-v1"
    )
    if _EVALUATION_ID.fullmatch(evaluation_id) is None:
        raise SystemExit("evaluation-id must be 3-80 lowercase safe characters")
    if not args.resume and any(
        path.is_file() for path in (predictions_path, provenance_path, report_path)
    ):
        raise SystemExit("SPIDER_REFUSE_OVERWRITE: existing artifact with --no-resume")
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
    if predictions and not provenance_path.is_file():
        raise SystemExit("SPIDER_RESUME_MISMATCH: predictions have no provenance")
    revision = git_provenance(root)
    if revision["git_commit"] == "unknown" or not revision["tracked_worktree_clean"]:
        raise SystemExit("release inference requires a known commit and clean tracked worktree")
    run_config = run_configuration(
        settings,
        correction_enabled=args.correction,
        profile=os.environ.get("TEXT2SQL_RESOURCE_PROFILE", "unspecified"),
    )
    index_root = settings.resolved_data_dir / "indexes/p3_1_semantic"
    index_pointer_sha256 = {
        db_id: sha256_file(index_root / db_id / "active.json")
        for db_id in sorted(manifest.database_sha256)
    }
    manifest_sha256 = sha256_file(manifest_path)
    if provenance_path.is_file():
        run_provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        verify_resume_provenance(
            run_provenance,
            revision=revision,
            evaluation_id=evaluation_id,
            manifest_sha256=manifest_sha256,
            index_pointer_sha256=index_pointer_sha256,
            run_config=run_config,
        )
    else:
        run_provenance = {
            **revision,
            "experiment_id": evaluation_id,
            "evaluator_version": "spider_release_v1",
            "oracle_evidence_used": False,
            "manifest_sha256": manifest_sha256,
            "index_pointer_sha256": index_pointer_sha256,
            "run_config": run_config,
            "database_runtime": {},
        }
    if args.evaluate_only and len(predictions) != len(cases):
        raise SystemExit("SPIDER_EVALUATION_REFUSED: incomplete prediction manifest")
    remaining = [] if args.evaluate_only else cases[len(predictions) :]
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
            previous_runtime = database_provenance.get(db_id)
            if previous_runtime is not None and previous_runtime != runtime.provenance:
                raise SystemExit(f"SPIDER_RESUME_MISMATCH: runtime identity for {db_id}")
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
    if args.inference_only:
        print(json.dumps({"status": "inference_complete", "completed": len(predictions)}))
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
        evaluation_id=evaluation_id,
    )
    print(json.dumps({key: value for key, value in report.items() if key != "details"}, indent=2))


if __name__ == "__main__":
    main()
