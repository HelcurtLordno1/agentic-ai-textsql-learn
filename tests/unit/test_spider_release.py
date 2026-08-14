from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from agentic_text2sql.contracts.sql import (
    CandidateRecord,
    DirectRunResult,
    DirectStatus,
    SqlCandidate,
)
from agentic_text2sql_eval.inference_runner import SmokePrediction
from agentic_text2sql_eval.spider_release import (
    create_release_manifest,
    evaluate_spider_release,
    execution_equal,
    load_release_cases,
)


def spider_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "spider"
    database_dir = root / "database" / "tiny"
    database_dir.mkdir(parents=True)
    database = database_dir / "tiny.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT)")
        connection.executemany("INSERT INTO items VALUES (?, ?)", [(1, "a"), (2, "b")])
    cases = [
        {"db_id": "tiny", "question": "Count items", "query": "SELECT COUNT(*) FROM items"},
        {"db_id": "tiny", "question": "List names", "query": "SELECT name FROM items"},
    ]
    (root / "dev.json").write_text(json.dumps(cases), encoding="utf-8")
    (root / "tables.json").write_text("[]", encoding="utf-8")
    return root


def test_release_manifest_pins_every_input_and_rejects_drift(tmp_path: Path) -> None:
    root = spider_fixture(tmp_path)
    manifest = create_release_manifest(root)
    path = tmp_path / "manifest.json"
    path.write_text(manifest.model_dump_json(), encoding="utf-8")
    loaded, cases = load_release_cases(root, path)
    assert loaded.case_count == len(cases) == 2
    assert loaded.database_count == 1
    assert [case.id for case in cases] == ["spider_dev_0000", "spider_dev_0001"]
    (root / "tables.json").write_text("[{}]", encoding="utf-8")
    with pytest.raises(ValueError, match="tables checksum"):
        load_release_cases(root, path)


def test_execution_equivalence_handles_row_and_column_permutations() -> None:
    gold = [[1, "a"], [2, "b"]]
    candidate = [["b", 2], ["a", 1]]
    assert execution_equal(candidate, gold, ordered=False)
    assert not execution_equal(candidate, gold, ordered=True)
    wide = [list(range(12))]
    assert execution_equal(wide, wide, ordered=False)


def test_release_evaluator_reports_hash_not_gold_sql(tmp_path: Path) -> None:
    root = spider_fixture(tmp_path)
    manifest = create_release_manifest(root)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")
    _, cases = load_release_cases(root, manifest_path)
    predictions = []
    for case in cases:
        sql = "SELECT COUNT(*) FROM items" if "Count" in case.question else "SELECT name FROM items"
        candidate = CandidateRecord(
            candidate=SqlCandidate(sql=sql, confidence=1),
            normalized_sql=sql,
            fingerprint="a" * 64,
            model_name="fake",
            prompt_version="test",
            catalog_hash="catalog",
        )
        predictions.append(
            SmokePrediction(
                case_id=case.id,
                result=DirectRunResult(
                    run_id=case.id,
                    question=case.question,
                    status=DirectStatus.SUCCEEDED,
                    route_reason="test",
                    prompt_versions={},
                    candidate=candidate,
                ),
            )
        )
    report_path = tmp_path / "report.json"
    report = evaluate_spider_release(
        spider_root=root,
        manifest=manifest,
        cases=cases,
        predictions=predictions,
        report_path=report_path,
        provenance={"model": "fake"},
    )
    assert report["result_accuracy"] == 1
    serialized = report_path.read_text(encoding="utf-8")
    assert '"gold_sql"' not in serialized
    assert "expected_result_hash" in serialized
