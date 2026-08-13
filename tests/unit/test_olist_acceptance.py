from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from agentic_text2sql.contracts.sql import DirectRunResult, DirectStatus
from agentic_text2sql_eval.inference_runner import SmokePrediction
from agentic_text2sql_eval.olist_acceptance import (
    OlistAcceptanceCase,
    _rows_equal,
    evaluate_olist_acceptance,
    load_olist_acceptance,
)


def test_row_comparison_respects_order_and_tolerance() -> None:
    assert _rows_equal([[2], [1.001]], [[1.0], [2]], order_matters=False, tolerance=0.01)
    assert not _rows_equal([[2], [1]], [[1], [2]], order_matters=True, tolerance=0)


def test_manifest_requires_exact_reviewed_partition(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_olist_acceptance(path)


def test_evaluator_hashes_gold_and_reports_slices(tmp_path: Path) -> None:
    database = tmp_path / "tiny.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE values_table(value REAL)")
        connection.execute("INSERT INTO values_table VALUES (1.0)")
    case = OlistAcceptanceCase(
        id="one",
        partition="dev",
        language="en",
        question="value?",
        difficulty="easy",
        required_concepts=("value",),
        gold_sql="SELECT value FROM values_table",
        tolerance=0.01,
        reviewed=True,
    )
    prediction = SmokePrediction(
        case_id="one",
        result=DirectRunResult(
            run_id="run",
            question="value?",
            status=DirectStatus.SUCCEEDED,
            route_reason="query",
            prompt_versions={},
            result_rows=[[1.005]],
            latency_ms={"total": 1},
        ),
    )
    report_path = tmp_path / "report.json"
    report = evaluate_olist_acceptance(
        cases=[case], predictions=[prediction], database=database, report_path=report_path
    )
    assert report["result_accuracy"] == 1
    assert report["valid_candidate_rate"] == 0
    assert report["first_pass_correct_rate"] == 1
    assert report["correction"]["attempted_count"] == 0
    assert report["by_language"]["en"]["correct"] == 1
    assert "gold_sql" not in report_path.read_text(encoding="utf-8")
    assert json.loads(report_path.read_text())["details"][0]["expected_result_hash"]
