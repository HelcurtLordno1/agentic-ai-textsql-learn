from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentic_text2sql.contracts.catalog import (
    CatalogSnapshot,
    ColumnInfo,
    ForeignKeyInfo,
    TableInfo,
)
from agentic_text2sql.contracts.retrieval import SchemaContext
from agentic_text2sql.contracts.sql import DirectStatus, SqlCandidate
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer3_generation.a1_prompt import (
    build_a1_prompt,
    build_evidence,
    complete_empty_relation_context,
)
from agentic_text2sql.layer6_application.a1_service import A1QueryService
from agentic_text2sql.settings import Settings


def context(catalog: CatalogSnapshot, columns: list[str]) -> SchemaContext:
    return SchemaContext(
        db_id=catalog.db_id,
        catalog_hash=catalog.catalog_hash,
        selected_tables=[t.name for t in catalog.tables],
        selected_columns=columns,
        joins=[],
        evidence=[],
        rendered_context="original rendering",
    )


@pytest.fixture()
def catalog() -> CatalogSnapshot:
    return CatalogSnapshot(
        db_id="renamed",
        catalog_hash="a" * 64,
        tables=(
            TableInfo(
                name="ledger",
                columns=(ColumnInfo(name="key", data_type="INT", primary_key_position=1),),
            ),
            TableInfo(
                name="rollup",
                kind="view",
                columns=(
                    ColumnInfo(name="parent", data_type="INT"),
                    ColumnInfo(name="n", data_type="INT"),
                ),
            ),
        ),
    )


def test_empty_view_completes_only_its_catalog_columns_without_mutating_selection(catalog) -> None:
    original = context(catalog, [])
    before = original.model_dump()
    with pytest.raises(ValueError, match="no grounded columns"):
        build_evidence("Count records", catalog, original, "")
    fixed = complete_empty_relation_context(catalog, original)
    assert original.model_dump() == before
    assert fixed.selected_tables == original.selected_tables
    assert set(fixed.selected_columns) == {"rollup.parent", "rollup.n"}
    assert fixed.evidence[-1].kind == "catalog_completion"
    prompt = build_a1_prompt(build_evidence("Count records", catalog, fixed, ""))
    assert "parent" in prompt and "rollup" in prompt
    assert fixed.estimated_tokens <= 1200


def test_working_context_and_prompt_are_exactly_preserved(catalog) -> None:
    original = context(catalog, ["rollup.n"])
    fixed = complete_empty_relation_context(catalog, original)
    assert fixed is original
    assert build_a1_prompt(build_evidence("Count records", catalog, fixed, "domain")) == (
        build_a1_prompt(build_evidence("Count records", catalog, original, "domain"))
    )


@pytest.mark.parametrize("kind", ["view", "table"])
def test_pk_free_relation_is_not_assumed_to_have_a_key(catalog, kind: str) -> None:
    c = catalog.model_copy(
        update={"tables": (catalog.tables[1].model_copy(update={"kind": kind}),)}
    )
    fixed = complete_empty_relation_context(c, context(c, []))
    assert set(fixed.selected_columns) == {"rollup.parent", "rollup.n"}
    assert "PRIMARY KEY" not in build_evidence("Count", c, fixed, "")[1].text


def test_composite_implicit_fk_makes_relation_nonempty_without_completion() -> None:
    parent = TableInfo(
        name="p",
        columns=tuple(
            ColumnInfo(name=n, data_type="INT", primary_key_position=i)
            for i, n in enumerate(["a", "b"], 1)
        ),
    )
    child = TableInfo(
        name="c",
        columns=(ColumnInfo(name="x", data_type="INT"), ColumnInfo(name="y", data_type="INT")),
        foreign_keys=(
            ForeignKeyInfo(
                from_columns=("x", "y"), target_table="p", target_columns=("None", "None")
            ),
        ),
    )
    catalog = CatalogSnapshot(db_id="composite", catalog_hash="c" * 64, tables=(parent, child))
    original = context(catalog, [])
    assert complete_empty_relation_context(catalog, original) is original
    assert '"x"' in build_evidence("Count", catalog, original, "")[2].text


@pytest.mark.parametrize(
    "field,value",
    [
        ("db_id", "alien"),
        ("catalog_hash", "b" * 64),
        ("selected_tables", ["invented"]),
        ("selected_columns", ["rollup.invented"]),
    ],
)
def test_bad_identity_or_unknown_schema_is_not_recovered(catalog, field, value) -> None:
    original = context(catalog, []).model_copy(update={field: value})
    with pytest.raises(ValueError):
        complete_empty_relation_context(catalog, original)


def test_wide_completion_fails_without_truncation_or_source_removal(catalog) -> None:
    original = context(catalog, [])
    with pytest.raises(ValueError, match="schema budget"):
        complete_empty_relation_context(catalog, original, token_budget=1)
    assert original.selected_columns == []
    empty_catalog = catalog.model_copy(update={"tables": (TableInfo(name="empty", columns=()),)})
    with pytest.raises(ValueError, match="no catalog columns"):
        complete_empty_relation_context(empty_catalog, context(empty_catalog, []))


def test_optin_recovery_reaches_generator_once_and_full_prompt_overflow_never_calls_it(
    tmp_path: Path,
) -> None:
    db = tmp_path / "source.sqlite"
    with sqlite3.connect(db) as con:
        con.executescript(
            "CREATE TABLE source(n INT); INSERT INTO source VALUES (1); "
            "CREATE VIEW summary AS SELECT n FROM source;"
        )
    full = SQLiteIntrospector().inspect(db, "renamed")
    original = context(full, ["source.n"])
    prompts = []

    class Provider:
        def generate_structured(self, *, prompt, response_model, model=None):
            prompts.append(prompt)
            return SqlCandidate(sql="SELECT COUNT(*) FROM summary", confidence=1)

    grounding = SimpleNamespace(ground=lambda *args: original, token_budget=1200)
    settings = Settings(_env_file=None, TEXT2SQL_RECOVER_EMPTY_RELATIONS=True)
    result = A1QueryService(Provider(), settings, grounding=grounding).run(
        "Count records", db, full
    )
    assert result.status is DirectStatus.SUCCEEDED and result.result_rows == [[1]]
    assert len(prompts) == result.assessment["actual_generation_requests"] == 1
    assert any(e["kind"] == "catalog_completion" for e in result.schema_context["evidence"])
    # Independent budget check on the actual complete prompt, before provider access.
    prompts.clear()
    settings = settings.model_copy(update={"input_token_budget": 256})
    long_question = "Count records " + "repeated " * 100
    result = A1QueryService(Provider(), settings, grounding=grounding).run(long_question, db, full)
    assert result.status is DirectStatus.GROUNDING_ERROR
    assert prompts == [] and result.assessment["actual_generation_requests"] == 0
    # Control still uses V4's failure boundary.
    settings = settings.model_copy(update={"recover_empty_relations": False})
    result = A1QueryService(Provider(), settings, grounding=grounding).run(
        "Count records", db, full
    )
    assert result.status is DirectStatus.GROUNDING_ERROR and prompts == []
