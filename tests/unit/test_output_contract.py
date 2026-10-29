from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agentic_text2sql.contracts.assessment import A1Trace, CandidateEvaluation, ClauseAssessment
from agentic_text2sql.contracts.catalog import CatalogSnapshot, ColumnInfo, TableInfo
from agentic_text2sql.contracts.sql import DirectStatus, SqlCandidate
from agentic_text2sql.contracts.validation import ErrorClass, PolicyDecision, ValidationReport
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer4_validation.output_contract import compile_output_contract
from agentic_text2sql.layer4_validation.owner_feedback import column_owner_feedback
from agentic_text2sql.layer6_application.a1_service import A1QueryService
from agentic_text2sql.settings import Settings
from tests.unit.test_a1_pipeline import QueueProvider


@pytest.fixture()
def catalog() -> CatalogSnapshot:
    return CatalogSnapshot(
        db_id="renamed",
        catalog_hash="output-fixture",
        tables=(
            TableInfo(
                name="performers",
                columns=(
                    ColumnInfo(name="id", data_type="INT", primary_key_position=1),
                    ColumnInfo(name="name", data_type="TEXT"),
                    ColumnInfo(name="age", data_type="INT"),
                ),
            ),
        ),
    )


def test_projection_keeps_filter_group_order_and_expands_removed_alias(
    catalog: CatalogSnapshot,
) -> None:
    draft = (
        "SELECT name, COUNT(*) AS n FROM performers WHERE age>20 "
        "GROUP BY name HAVING n>1 ORDER BY n DESC"
    )
    contract = compile_output_contract(
        "Return the name of performers with the most records.", draft, catalog
    )
    assert contract.eligible and contract.planned_sql
    assert contract.allowed_fields == ("select",)
    assert "HAVING COUNT(*) > 1" in contract.planned_sql
    assert "ORDER BY COUNT(*) DESC" in contract.planned_sql
    with sqlite3.connect(":memory:") as db:
        db.executescript(
            "CREATE TABLE performers(id INT,name TEXT,age INT); "
            "INSERT INTO performers VALUES(1,'a',21),(2,'a',22),(3,'b',10)"
        )
        assert db.execute(contract.planned_sql).fetchall() == [("a",)]


@pytest.mark.parametrize(
    "question,sql",
    [
        ("Return the name and age.", "SELECT name, age FROM performers"),
        (
            "Return the name and number of records.",
            "SELECT name, COUNT(*) FROM performers GROUP BY name",
        ),
        ("Return all performers.", "SELECT name, age FROM performers"),
        ("Return the name with age.", "SELECT name, age FROM performers"),
        ("Return the name of performers and their age.", "SELECT name, age FROM performers"),
        ("Return the name of performers.", "SELECT DISTINCT name, age FROM performers"),
        ("Return the name of performers.", "SELECT name, COUNT(*) FROM performers"),
        ("Return the name of performers.", "SELECT name, age FROM performers ORDER BY 2"),
        ("Return the name of performers.", "SELECT * FROM performers"),
        ("Return the name of performers.", "SELECT p.* FROM performers p"),
        (
            "Return the name of performers.",
            "WITH x AS (SELECT * FROM performers) SELECT name, age FROM x",
        ),
        ("How old are performers?", "SELECT name, age FROM performers"),
    ],
)
def test_ambiguous_or_unsupported_projection_abstains(
    catalog: CatalogSnapshot, question: str, sql: str
) -> None:
    assert not compile_output_contract(question, sql, catalog).eligible


def test_multiple_output_owners_are_not_resolved_from_the_draft(catalog: CatalogSnapshot) -> None:
    other = catalog.tables[0].model_copy(update={"name": "others"})
    ambiguous = catalog.model_copy(update={"tables": (*catalog.tables, other)})
    assert not compile_output_contract(
        "Return the name of performers.",
        "SELECT p.name,p.age FROM performers p JOIN others o ON p.id=o.id",
        ambiguous,
    ).eligible


@pytest.mark.parametrize("relation", ["archive_orders", "live_orders"])
def test_grouped_count_ranking_with_explicit_tie_policy(relation: str) -> None:
    cat = CatalogSnapshot(
        db_id="renamed",
        catalog_hash="ranking-fixture",
        tables=(
            TableInfo(
                name=relation,
                columns=(
                    ColumnInfo(name="id", data_type="INT", primary_key_position=1),
                    ColumnInfo(name="created_at", data_type="TEXT"),
                ),
            ),
        ),
    )
    sql = (
        "SELECT STRFTIME('%Y-%m',created_at) AS month,COUNT(*) AS n "
        f"FROM {relation} GROUP BY month ORDER BY month"
    )
    question = "Tháng nào có nhiều đơn nhất? Trả tháng và số đơn, hòa thì tháng tăng dần."
    c = compile_output_contract(question, sql, cat)
    assert c.eligible and c.planned_sql
    with sqlite3.connect(":memory:") as db:
        db.execute(f"CREATE TABLE {relation}(id INTEGER PRIMARY KEY,created_at TEXT)")
        db.executemany(
            f"INSERT INTO {relation} VALUES(?,?)",
            [(1, "2020-02-01"), (2, "2020-02-02"), (3, "2020-01-01"), (4, "2020-01-02")],
        )
        assert db.execute(c.planned_sql).fetchall() == [("2020-01", 2)]
    assert not compile_output_contract(question, c.planned_sql, cat).eligible


@pytest.mark.parametrize(
    "suffix",
    [
        "",
        " Trả mọi đồng hạng.",
        " Không lấy top.",
    ],
)
def test_ranking_without_singular_tie_license_abstains(suffix: str) -> None:
    cat = CatalogSnapshot(
        db_id="tiny",
        catalog_hash="ranking-fixture",
        tables=(
            TableInfo(
                name="orders",
                columns=(
                    ColumnInfo(name="id", data_type="INT", primary_key_position=1),
                    ColumnInfo(name="label", data_type="TEXT"),
                ),
            ),
        ),
    )
    assert not compile_output_contract(
        "Nhóm nào có nhiều đơn nhất?" + suffix,
        "SELECT label,COUNT(*) FROM orders GROUP BY label",
        cat,
    ).eligible


def test_owner_feedback_contains_real_catalog_facts_only(catalog: CatalogSnapshot) -> None:
    facts = column_owner_feedback("Unknown column: summary.age", catalog)
    assert facts["failed_reference"] == "summary.age"
    assert facts["existing_owners"] == [
        {"relation": "performers", "kind": "table", "columns": ["age", "id"]}
    ]
    assert not column_owner_feedback("Unknown column: missing", catalog)
    assert not column_owner_feedback("Write is prohibited", catalog)


def test_integration_uses_one_model_call_and_retains_draft(tmp_path: Path) -> None:
    path = tmp_path / "fixture.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript(
            "CREATE TABLE performers(id INTEGER PRIMARY KEY,name TEXT,age INT);"
            "INSERT INTO performers VALUES(1,'a',10),(2,'a',20),(3,'b',20)"
        )
    provider = QueueProvider(
        [
            SqlCandidate(
                sql="SELECT name,COUNT(*) AS n FROM performers GROUP BY name ORDER BY n DESC",
                confidence=1,
            )
        ]
    )
    settings = Settings(
        TEXT2SQL_PIPELINE_MODE="a1",
        TEXT2SQL_CRITIC_MODE="repair",
        TEXT2SQL_COMPUTE_POLICY="obligation",
        TEXT2SQL_DETERMINISTIC_REPAIR=True,
        TEXT2SQL_BOUNDED_OUTPUT_CONTRACTS=True,
    )
    service = A1QueryService(provider, settings, correction_enabled=True)
    result = service.run(
        "Return the name of performers with the most records.",
        path,
        SQLiteIntrospector().inspect(path, "tiny"),
    )
    assert result.status is DirectStatus.SUCCEEDED
    assert result.result_rows == [["a"], ["b"]]
    assert result.assessment["repair_admitted"]
    assert result.assessment["actual_generation_requests"] == 1
    assert len(result.assessment["evaluations"]) == 2
    assert result.assessment["evaluations"][1]["origin"] == "deterministic"
    assert result.assessment["semantic_status"] == "UNVERIFIED"
    assert len(provider.prompts) == 1


def test_new_features_default_off() -> None:
    settings = Settings(_env_file=None)
    assert not settings.bounded_output_contracts and not settings.owner_repair_feedback


def test_optional_owner_facts_cannot_break_a_working_prompt_budget(
    catalog: CatalogSnapshot,
) -> None:
    draft = CandidateEvaluation(
        raw_sql="SELECT age FROM summary",
        policy=PolicyDecision(allowed=False, error_class=ErrorClass.UNKNOWN_COLUMN),
        validation=ValidationReport(
            accepted=False,
            error_class=ErrorClass.UNKNOWN_COLUMN,
            safe_message="Unknown column: summary.age",
        ),
        checks=ClauseAssessment(),
    )
    trace = A1Trace(critic_mode="repair", generation_format="json", max_requests=3)
    prefix = "schema " * 150
    control = A1QueryService(QueueProvider([]), Settings(_env_file=None))
    original = control._repair_prompt(prefix, draft, trace, catalog)
    from agentic_text2sql.layer2_grounding.context_packer import estimate_tokens

    candidate = A1QueryService(
        QueueProvider([]),
        Settings(
            _env_file=None,
            TEXT2SQL_OWNER_REPAIR_FEEDBACK=True,
            TEXT2SQL_INPUT_TOKEN_BUDGET=estimate_tokens(original),
        ),
    )
    assert candidate._repair_prompt(prefix, draft, trace, catalog) == original


def test_scalar_average_preserves_review_row_weighting() -> None:
    cat = CatalogSnapshot(
        db_id="tiny",
        catalog_hash="scalar-fixture",
        tables=(
            TableInfo(name="ratings", columns=(ColumnInfo(name="rating", data_type="INTEGER"),)),
            TableInfo(
                name="summary",
                kind="view",
                columns=(ColumnInfo(name="average_rating", data_type="REAL"),),
            ),
        ),
    )
    c = compile_output_contract(
        "What is the average rating rounded to 2 decimals?",
        "SELECT ROUND(average_rating,2) FROM summary",
        cat,
    )
    assert c.eligible and c.planned_sql
    with sqlite3.connect(":memory:") as db:
        db.executescript(
            "CREATE TABLE ratings(rating INT);INSERT INTO ratings VALUES(1),(5),(5),(5)"
        )
        assert db.execute(c.planned_sql).fetchall() == [(4.0,)]
    assert not compile_output_contract(
        "What is the average rating rounded to 2 decimals?", c.planned_sql, cat
    ).eligible
    assert not compile_output_contract(
        "What is the average rating per customer rounded to 2 decimals?",
        "SELECT average_rating FROM summary",
        cat,
    ).eligible
    duplicate = cat.model_copy(
        update={"tables": (*cat.tables, cat.tables[0].model_copy(update={"name": "alternate"}))}
    )
    assert not compile_output_contract(
        "What is the average rating rounded to 2 decimals?",
        "SELECT average_rating FROM summary",
        duplicate,
    ).eligible
