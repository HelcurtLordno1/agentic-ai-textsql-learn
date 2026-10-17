from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agentic_text2sql.contracts.sql import DirectStatus, SqlCandidate
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer4_validation.executor import ReadOnlySQLiteExecutor
from agentic_text2sql.layer4_validation.policy import SQLSafetyPolicy
from agentic_text2sql.layer6_application.a1_service import A1QueryService
from agentic_text2sql.settings import Settings


@pytest.fixture()
def database(tmp_path: Path) -> Path:
    path = tmp_path / "renamed.sqlite"
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE readings(n INT PRIMARY KEY, value REAL, zone TEXT)")
        con.executemany(
            "INSERT INTO readings VALUES (?, ?, ?)", [(n, 0, "low") for n in range(230)]
        )
        con.executemany(
            "INSERT INTO readings VALUES (?, ?, ?)", [(230, 1000, "high"), (231, None, "null")]
        )
    return path


@pytest.mark.parametrize(
    "sql",
    [
        "WITH mean AS (SELECT AVG(value) AS mean_value FROM readings) SELECT mean_value FROM mean",
        "SELECT mean_value FROM (SELECT AVG(value) AS mean_value FROM readings) AS d",
        "WITH mean AS (SELECT AVG(value) AS mean_value FROM readings), "
        "counts AS (SELECT zone, COUNT(*) AS n_above FROM readings "
        "WHERE value > (SELECT mean_value FROM mean) GROUP BY zone) SELECT * FROM counts",
        "WITH mean AS (SELECT AVG(value) AS mean_value FROM readings), "
        "copy AS (SELECT mean_value FROM mean) SELECT mean_value FROM copy",
    ],
)
def test_named_outputs_resolve_only_in_their_selected_source(database: Path, sql: str) -> None:
    catalog = SQLiteIntrospector().inspect(database, "renamed")
    assert not SQLSafetyPolicy().evaluate(sql, catalog).allowed
    decision = SQLSafetyPolicy(resolve_derived_columns=True).evaluate(sql, catalog)
    assert decision.allowed and decision.normalized_sql
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as con:
        assert con.execute(decision.normalized_sql).fetchall() == con.execute(sql).fetchall()


@pytest.mark.parametrize(
    "sql",
    [
        "WITH mean AS (SELECT AVG(value) AS mean_value FROM readings) "
        "SELECT mean_value FROM readings",
        "WITH mean AS (SELECT AVG(value) AS mean_value FROM readings), "
        "bad AS (SELECT mean_value FROM readings) SELECT * FROM bad",
        "WITH mean AS (SELECT AVG(value) AS mean_value FROM readings) "
        "SELECT mean_value FROM readings AS mean",
        "WITH a AS (SELECT AVG(value) AS v FROM readings), "
        "b AS (SELECT AVG(value) AS v FROM readings) SELECT v FROM a CROSS JOIN b",
        "WITH mean AS (SELECT AVG(invented) AS mean_value FROM readings) "
        "SELECT mean_value FROM mean",
        "WITH mean(v) AS (SELECT AVG(value) FROM readings) SELECT v FROM mean",
        "WITH mean(v) AS (SELECT AVG(value) FROM readings) SELECT invented FROM mean",
        "SELECT mean_value FROM (SELECT * FROM (SELECT AVG(value) AS mean_value FROM readings)) d",
        "SELECT invented FROM readings",
        "WITH mean AS (DELETE FROM readings RETURNING value) SELECT * FROM mean",
        "WITH mean AS (SELECT load_extension('evil') AS mean_value) SELECT mean_value FROM mean",
        "WITH mean AS (SELECT * FROM sqlite_master) SELECT * FROM mean",
    ],
)
def test_sibling_shadow_unknown_ambiguity_and_write_do_not_gain_permission(
    database: Path, sql: str
) -> None:
    catalog = SQLiteIntrospector().inspect(database, "renamed")
    assert not SQLSafetyPolicy(resolve_derived_columns=True).evaluate(sql, catalog).allowed


def test_nested_aggregate_full_result_and_preview_have_distinct_bounds(database: Path) -> None:
    catalog = SQLiteIntrospector().inspect(database, "renamed")
    sql = "SELECT n FROM readings WHERE value < (SELECT AVG(value) FROM readings)"
    control = SQLSafetyPolicy().evaluate(sql, catalog)
    candidate = SQLSafetyPolicy(resolve_derived_columns=True).evaluate(sql, catalog)
    assert candidate == control and not candidate.limit_injected
    assert candidate.normalized_sql
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as con:
        rows = con.execute(candidate.normalized_sql).fetchall()
        assert rows == con.execute(sql).fetchall() and len(rows) == 230
    preview = ReadOnlySQLiteExecutor().execute(database, candidate.normalized_sql)
    assert preview.truncated and len(preview.rows) == 200


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT zone, COUNT(*) FROM readings GROUP BY zone",
        "SELECT n, ROW_NUMBER() OVER (ORDER BY n) AS position FROM readings",
        "SELECT n FROM readings UNION SELECT n FROM readings",
        "SELECT COUNT(*) FROM readings WHERE value IS NULL",
        "SELECT n FROM readings ORDER BY n DESC LIMIT 7",
    ],
)
def test_existing_accepted_policy_sql_stays_identical(database: Path, sql: str) -> None:
    catalog = SQLiteIntrospector().inspect(database, "renamed")
    before = SQLSafetyPolicy().evaluate(sql, catalog)
    assert before.allowed
    assert SQLSafetyPolicy(resolve_derived_columns=True).evaluate(sql, catalog) == before


def test_service_uses_same_policy_for_precheck_and_executor(database: Path) -> None:
    catalog = SQLiteIntrospector().inspect(database, "renamed")
    sql = "WITH mean AS (SELECT AVG(value) AS mean_value FROM readings) SELECT mean_value FROM mean"

    class Provider:
        def generate_structured(self, **kwargs):
            return SqlCandidate(sql=sql, confidence=1)

    settings = Settings(_env_file=None, TEXT2SQL_RESOLVE_DERIVED_COLUMNS=True)
    result = A1QueryService(Provider(), settings).run("Find the average reading", database, catalog)
    assert result.status is DirectStatus.SUCCEEDED
    assert result.assessment["actual_generation_requests"] == 1
    assert not result.assessment["repair_attempted"]
