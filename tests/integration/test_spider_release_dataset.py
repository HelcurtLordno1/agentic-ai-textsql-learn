from __future__ import annotations

from pathlib import Path

import pytest

from agentic_text2sql.contracts.sql import (
    CandidateRecord,
    DirectRunResult,
    DirectStatus,
    SqlCandidate,
)
from agentic_text2sql.settings import discover_project_root
from agentic_text2sql_eval.inference_runner import SmokePrediction
from agentic_text2sql_eval.spider_release import evaluate_spider_release, load_release_cases


def test_full_spider_release_evaluator_accepts_exact_gold(tmp_path: Path) -> None:
    root = discover_project_root()
    spider_root = root / "data/raw/spider/spider_data"
    manifest_path = root / "evals/configs/spider-release-1034.json"
    if not (spider_root / "dev.json").is_file():
        pytest.skip("full Spider dev is not installed")
    manifest, cases = load_release_cases(spider_root, manifest_path)
    predictions = [
        SmokePrediction(
            case_id=case.id,
            result=DirectRunResult(
                run_id=case.id,
                question=case.question,
                status=DirectStatus.SUCCEEDED,
                route_reason="evaluator-self-test",
                prompt_versions={},
                candidate=CandidateRecord(
                    candidate=SqlCandidate(sql=case.gold_sql, confidence=1),
                    normalized_sql=case.gold_sql,
                    fingerprint="a" * 64,
                    model_name="exact-gold-fixture",
                    prompt_version="evaluator-self-test",
                    catalog_hash="fixture",
                ),
            ),
        )
        for case in cases
    ]
    report = evaluate_spider_release(
        spider_root=spider_root,
        manifest=manifest,
        cases=cases,
        predictions=predictions,
        report_path=tmp_path / "spider-self-test.json",
        provenance={"purpose": "evaluator-self-test"},
    )
    assert report["case_count"] == 1034
    assert report["result_correct_count"] == 1034
    assert report["result_accuracy"] == 1


def test_laptop_manifest_is_disjoint_and_stratified() -> None:
    root = discover_project_root()
    spider_root = root / "data/raw/spider/spider_data"
    if not (spider_root / "dev.json").is_file():
        pytest.skip("full Spider dev is not installed")
    manifest, cases = load_release_cases(spider_root, root / "evals/configs/spider-laptop-200.json")
    assert manifest.benchmark_profile == "laptop-stratified"
    assert manifest.case_count == len(cases) == 200
    assert manifest.database_count == len({case.db_id for case in cases}) == 20
    assert sum(case.partition == "regression" for case in cases) == 100
    assert sum(case.partition == "holdout" for case in cases) == 100
    assert len({case.dev_index for case in cases}) == 200
