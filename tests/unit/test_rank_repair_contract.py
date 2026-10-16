from __future__ import annotations

import pytest

from agentic_text2sql.contracts.catalog import CatalogSnapshot, ColumnInfo, TableInfo
from agentic_text2sql.contracts.validation import ValidationReport
from agentic_text2sql.layer4_validation.clause_critic import assess_clauses
from agentic_text2sql.layer4_validation.repair_contract import (
    admit_contract_repair,
    compile_repair_contract,
)


@pytest.fixture()
def catalog() -> CatalogSnapshot:
    return CatalogSnapshot(
        db_id="tiny",
        catalog_hash="contract-fixture",
        tables=(
            TableInfo(
                name="scores",
                columns=(
                    ColumnInfo(name="id", data_type="INT"),
                    ColumnInfo(name="score", data_type="INT"),
                ),
            ),
        ),
    )


def test_missing_order_has_independent_metric_binding(catalog: CatalogSnapshot) -> None:
    question = "Show top 1 highest scores"
    draft = "SELECT score FROM scores LIMIT 3"
    before = assess_clauses(question, draft, catalog)
    contract = compile_repair_contract(question, draft, catalog, before)
    assert contract.eligible and contract.planned_sql is not None
    assert contract.metric == "scores.score"
    assert set(contract.allowed_fields) == {"order", "limit"}
    after = assess_clauses(question, contract.planned_sql, catalog)
    assert admit_contract_repair(
        contract,
        contract.planned_sql,
        ValidationReport(accepted=True),
        before,
        after,
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT score FROM scores ORDER BY id ASC LIMIT 1",
        "SELECT -score AS score FROM scores ORDER BY score ASC LIMIT 1",
        "SELECT id AS score, score AS score FROM scores ORDER BY score ASC LIMIT 1",
        "SELECT MAX(score) AS score FROM scores",
        "SELECT score FROM scores ORDER BY score ASC LIMIT 1 OFFSET 1",
    ],
)
def test_wrong_metric_derived_metric_and_scope_are_not_licensed(
    catalog: CatalogSnapshot,
    sql: str,
) -> None:
    question = "Show top 1 highest scores"
    checks = assess_clauses(question, sql, catalog)
    assert not compile_repair_contract(question, sql, catalog, checks).eligible
    if "OFFSET" not in sql:
        assert "EXPLICIT_RANK_DIRECTION" not in checks.contradictions


def test_valid_executable_untargeted_edit_is_rejected(catalog: CatalogSnapshot) -> None:
    question = "Show top 1 highest scores"
    draft = "SELECT score FROM scores ORDER BY score ASC LIMIT 1"
    before = assess_clauses(question, draft, catalog)
    contract = compile_repair_contract(question, draft, catalog, before)
    changed = "SELECT id FROM scores WHERE score > 10 ORDER BY score DESC LIMIT 1"
    after = assess_clauses(question, changed, catalog)
    assert not admit_contract_repair(
        contract,
        changed,
        ValidationReport(accepted=True),
        before,
        after,
    )


def test_ambiguous_catalog_binding_is_not_resolved_from_draft(catalog: CatalogSnapshot) -> None:
    other = TableInfo(name="other", columns=(ColumnInfo(name="score", data_type="INT"),))
    ambiguous = catalog.model_copy(update={"tables": (*catalog.tables, other)})
    question = "Show top 1 highest scores"
    draft = "SELECT score FROM scores ORDER BY score ASC LIMIT 1"
    checks = assess_clauses(question, draft, ambiguous)
    assert not compile_repair_contract(question, draft, ambiguous, checks).eligible


@pytest.mark.parametrize(
    "question",
    [
        "Show top 1 scores without ranking",
        "Show top 1 highest scores with ties",
        "Show top 1 highest score or lowest score",
    ],
)
def test_ambiguous_intent_never_gets_a_contract(
    catalog: CatalogSnapshot,
    question: str,
) -> None:
    sql = "SELECT score FROM scores ORDER BY score ASC LIMIT 1"
    checks = assess_clauses(question, sql, catalog)
    assert not compile_repair_contract(question, sql, catalog, checks).eligible
