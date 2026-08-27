from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agentic_text2sql_eval.failure_analysis import (
    FailureCause,
    ReviewerLabel,
    analyze_spider_failures,
    calculate_review_agreement,
    inspect_sql,
)
from agentic_text2sql_eval.result_comparator import compare_reports
from agentic_text2sql_eval.spider_release import LoadedSpiderCase


def _spider_root(tmp_path: Path) -> Path:
    root = tmp_path / "spider"
    database_dir = root / "database" / "tiny"
    database_dir.mkdir(parents=True)
    with sqlite3.connect(database_dir / "tiny.sqlite") as connection:
        connection.execute(
            "CREATE TABLE items(id INTEGER PRIMARY KEY, category_id INTEGER, value INTEGER)"
        )
        connection.execute("CREATE TABLE categories(id INTEGER PRIMARY KEY, name TEXT)")
        connection.executemany("INSERT INTO categories VALUES (?, ?)", [(1, "a"), (2, "b")])
        connection.executemany("INSERT INTO items VALUES (?, ?, ?)", [(1, 1, 10), (2, 1, 20)])
    return root


def _case(case_id: str, gold_sql: str) -> LoadedSpiderCase:
    return LoadedSpiderCase(
        id=case_id,
        dev_index=0,
        db_id="tiny",
        question="test",
        gold_sql=gold_sql,
        complexity="medium",
        partition="holdout",
    )


def test_sql_structure_contains_hashes_not_literal_values() -> None:
    structure = inspect_sql("SELECT SUM(value) FROM items WHERE category_id = 42")
    serialized = structure.model_dump_json()
    assert structure.aggregate_functions == ("sum",)
    assert structure.literal_fingerprints
    assert "42" not in serialized


def test_failure_analysis_emits_reviewable_evidence_without_gold_sql(tmp_path: Path) -> None:
    root = _spider_root(tmp_path)
    cases = [
        _case("spider_holdout_0000", "SELECT SUM(value) FROM items"),
        _case(
            "spider_holdout_0001",
            "SELECT categories.name FROM items JOIN categories "
            "ON items.category_id = categories.id",
        ),
    ]
    report = {
        "evaluation_id": "baseline",
        "release_status": "complete",
        "provenance": {"git_commit": "a" * 40},
        "details": [
            {
                "id": cases[0].id,
                "status": "SUCCEEDED",
                "result_correct": False,
                "failure_category": "EXECUTION_MISMATCH",
                "generated_sql": "SELECT COUNT(value) FROM items",
            },
            {
                "id": cases[1].id,
                "status": "SUCCEEDED",
                "result_correct": False,
                "failure_category": "EXECUTION_MISMATCH",
                "generated_sql": "SELECT category_id FROM items",
            },
        ],
    }
    analysis = analyze_spider_failures(
        spider_root=root,
        cases=cases,
        release_report=report,
        source_report_sha256="b" * 64,
        analysis_id="r0-test",
    )
    assert analysis.failure_count == analysis.review_required_count == 2
    assert analysis.cases[0].primary_cause is FailureCause.AGGREGATION_OR_GRAIN
    assert analysis.cases[1].primary_cause is FailureCause.JOIN_OR_SOURCE
    serialized = analysis.model_dump_json()
    assert "gold_sql" not in serialized
    assert "SELECT SUM" not in serialized
    assert "categories.name" not in serialized


def test_review_agreement_requires_independent_complete_reviewers() -> None:
    labels_a = [
        ReviewerLabel(reviewer_id="a", case_id="1", primary_cause=FailureCause.PROJECTION),
        ReviewerLabel(reviewer_id="a", case_id="2", primary_cause=FailureCause.FILTER_OR_VALUE),
    ]
    labels_b = [
        ReviewerLabel(reviewer_id="b", case_id="1", primary_cause=FailureCause.PROJECTION),
        ReviewerLabel(reviewer_id="b", case_id="2", primary_cause=FailureCause.JOIN_OR_SOURCE),
    ]
    agreement = calculate_review_agreement(labels_a, labels_b)
    assert agreement.exact_agreement == 0.5
    with pytest.raises(ValueError, match="distinct reviewers"):
        calculate_review_agreement(
            labels_a, [item.model_copy(update={"reviewer_id": "a"}) for item in labels_b]
        )


def test_paired_comparator_preserves_wins_and_regressions() -> None:
    baseline = {
        "evaluation_id": "before",
        "release_status": "complete",
        "details": [{"id": "a", "result_correct": False}, {"id": "b", "result_correct": True}],
    }
    challenger = {
        "evaluation_id": "after",
        "release_status": "complete",
        "details": [{"id": "a", "result_correct": True}, {"id": "b", "result_correct": False}],
    }
    comparison = compare_reports(baseline, challenger)
    assert comparison.wins == comparison.losses == 1
    assert comparison.net_change == 0


def test_paired_comparator_rejects_different_manifests() -> None:
    baseline = {
        "release_status": "complete",
        "details": [{"id": "a", "result_correct": False}],
    }
    challenger = {
        "release_status": "complete",
        "details": [{"id": "b", "result_correct": True}],
    }
    with pytest.raises(ValueError, match="same case IDs"):
        compare_reports(baseline, challenger)
