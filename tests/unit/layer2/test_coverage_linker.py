"""Model-free checks for the opt-in schema coverage strategy."""

import pytest

from agentic_text2sql.contracts.catalog import (
    CatalogSnapshot,
    ColumnInfo,
    ForeignKeyInfo,
    TableInfo,
)
from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.retrieval import CatalogDocument, RankedDocument, RetrievalResult
from agentic_text2sql.layer2_grounding.schema_linker import link_schema


def _catalog() -> CatalogSnapshot:
    return CatalogSnapshot(
        db_id="events",
        catalog_hash="a" * 64,
        tables=(
            TableInfo(
                name="concert",
                columns=(
                    ColumnInfo(name="concert_id", data_type="INTEGER", primary_key_position=1),
                    ColumnInfo(name="stadium_id", data_type="INTEGER"),
                    ColumnInfo(name="attendance", data_type="INTEGER"),
                ),
                foreign_keys=(
                    ForeignKeyInfo(
                        from_columns=("stadium_id",),
                        target_table="stadium",
                        target_columns=("stadium_id",),
                    ),
                ),
            ),
            TableInfo(
                name="stadium",
                columns=(
                    ColumnInfo(name="stadium_id", data_type="INTEGER", primary_key_position=1),
                    ColumnInfo(name="name", data_type="TEXT"),
                    ColumnInfo(name="capacity", data_type="INTEGER"),
                ),
            ),
            TableInfo(name="ticket", columns=(ColumnInfo(name="price", data_type="REAL"),)),
        ),
    )


def _retrieval(catalog: CatalogSnapshot) -> RetrievalResult:
    concert = CatalogDocument(
        document_id="events.concert.attendance",
        db_id="events",
        kind="column",
        table="concert",
        column="attendance",
        description="concert attendance",
        catalog_hash=catalog.catalog_hash,
    )
    return RetrievalResult(
        db_id="events",
        mode="hybrid",
        candidates=(RankedDocument(document=concert, score=1, sources=("bm25",)),),
        estimated_tokens=10,
        catalog_hash=catalog.catalog_hash,
    )


def _plan() -> LogicalPlan:
    return LogicalPlan(
        question_language="en",
        task_type="ranking",
        metrics=["concert count"],
        dimensions=["stadium name"],
        required_concepts=["stadiums", "concerts"],
    )


def test_full_schema_fits_and_restores_unretrieved_owner_and_columns() -> None:
    catalog = _catalog()
    context = link_schema(
        _plan(),
        _retrieval(catalog),
        catalog,
        mode="coverage",
        question="Which stadiums hosted the most concerts?",
        token_budget=300,
    )
    assert set(context.selected_tables) == {"concert", "stadium", "ticket"}
    assert "stadium.name" in context.selected_columns
    assert "stadium.capacity" in context.selected_columns
    assert "concert.stadium_id = stadium.stadium_id" in context.joins
    assert context.estimated_tokens <= 300


def test_large_schema_keeps_unretrieved_lexical_owner_and_fk_path() -> None:
    catalog = _catalog()
    context = link_schema(
        _plan(),
        _retrieval(catalog),
        catalog,
        mode="coverage",
        question="Which stadiums hosted the most concerts?",
        max_tables=2,
        token_budget=130,
    )
    assert context.selected_tables == ["concert", "stadium"]
    assert context.joins == ["concert.stadium_id = stadium.stadium_id"]
    assert "stadium.name" in context.selected_columns
    assert context.estimated_tokens <= 130


def test_proven_required_owner_and_column_fail_closed_under_budget() -> None:
    catalog = _catalog()
    with pytest.raises(ValueError, match="required owner coverage"):
        link_schema(
            _plan(),
            _retrieval(catalog),
            catalog,
            mode="coverage",
            max_tables=2,
            token_budget=8,
            preferred_tables=("stadium",),
            required_columns=("stadium.name",),
        )


def test_foreign_retrieval_document_is_rejected() -> None:
    catalog = _catalog()
    retrieval = _retrieval(catalog)
    foreign = retrieval.model_copy(
        update={
            "candidates": (
                retrieval.candidates[0].model_copy(
                    update={
                        "document": retrieval.candidates[0].document.model_copy(
                            update={"catalog_hash": "b" * 64}
                        )
                    }
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="stale or foreign"):
        link_schema(_plan(), foreign, catalog, mode="coverage")


def test_anti_join_population_owner_is_kept_across_another_schema() -> None:
    catalog = CatalogSnapshot(
        db_id="vehicles",
        catalog_hash="b" * 64,
        tables=(
            TableInfo(
                name="countries",
                columns=(
                    ColumnInfo(name="country_id", data_type="INTEGER", primary_key_position=1),
                    ColumnInfo(name="name", data_type="TEXT"),
                ),
            ),
            TableInfo(
                name="car_makers",
                columns=(
                    ColumnInfo(name="maker_id", data_type="INTEGER", primary_key_position=1),
                    ColumnInfo(name="country_id", data_type="INTEGER"),
                ),
                foreign_keys=(
                    ForeignKeyInfo(
                        from_columns=("country_id",),
                        target_table="countries",
                        target_columns=("country_id",),
                    ),
                ),
            ),
            TableInfo(name="models", columns=(ColumnInfo(name="model_id", data_type="INTEGER"),)),
        ),
    )
    document = CatalogDocument(
        document_id="vehicles.car_makers",
        db_id="vehicles",
        kind="table",
        table="car_makers",
        description="car makers",
        catalog_hash=catalog.catalog_hash,
    )
    retrieval = RetrievalResult(
        db_id="vehicles",
        mode="bm25",
        candidates=(RankedDocument(document=document, score=1, sources=("bm25",)),),
        estimated_tokens=5,
        catalog_hash=catalog.catalog_hash,
    )
    plan = LogicalPlan(
        question_language="en",
        task_type="set",
        required_concepts=["countries", "car makers"],
    )
    context = link_schema(
        plan,
        retrieval,
        catalog,
        mode="coverage",
        max_tables=2,
        question="Which countries have no car makers?",
        token_budget=150,
    )
    assert context.selected_tables == ["car_makers", "countries"]
    assert "countries.name" in context.selected_columns
    assert context.joins == ["car_makers.country_id = countries.country_id"]


def test_legacy_default_remains_identical_when_coverage_is_disabled() -> None:
    catalog = _catalog()
    default = link_schema(_plan(), _retrieval(catalog), catalog)
    explicit_legacy = link_schema(_plan(), _retrieval(catalog), catalog, mode="legacy")
    assert default.model_dump(mode="json") == explicit_legacy.model_dump(mode="json")
