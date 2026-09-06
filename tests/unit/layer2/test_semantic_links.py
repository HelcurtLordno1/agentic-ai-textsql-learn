from pathlib import Path

from agentic_text2sql.contracts.catalog import (
    CatalogSnapshot,
    ColumnInfo,
    ForeignKeyInfo,
    TableInfo,
)
from agentic_text2sql.contracts.planning import DecomposedQuestion, LogicalPlan, SemanticRole
from agentic_text2sql.contracts.retrieval import (
    CatalogDocument,
    RankedDocument,
    RetrievalResult,
    SchemaContext,
)
from agentic_text2sql.layer2_grounding.fk_graph import minimal_join_closure
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer2_grounding.schema_linker import link_schema
from agentic_text2sql.layer2_grounding.semantic_links import build_semantic_link_plan
from agentic_text2sql.layer2_grounding.service import exact_entity_tables

ROOT = Path(__file__).resolve().parents[3]


def test_exact_entity_owner_ignores_olist_dataset_boilerplate() -> None:
    catalog = SQLiteIntrospector().inspect(ROOT / "data/processed/olist.sqlite", "olist")
    assert exact_entity_tables(catalog, ["orders"]) == ("olist_orders_dataset",)


def test_semantic_links_keep_owner_and_evidence_provenance() -> None:
    catalog = SQLiteIntrospector().inspect(
        ROOT / "data/samples/synthetic_commerce_tiny.sqlite", "synthetic"
    )
    documents = (
        CatalogDocument(
            document_id="synthetic.order_items.price",
            db_id="synthetic",
            kind="column",
            table="order_items",
            column="price",
            description="revenue price measure",
            catalog_hash=catalog.catalog_hash,
        ),
        CatalogDocument(
            document_id="synthetic.products.category",
            db_id="synthetic",
            kind="column",
            table="products",
            column="category",
            description="product category dimension",
            catalog_hash=catalog.catalog_hash,
        ),
    )
    retrieval = RetrievalResult(
        db_id="synthetic",
        mode="hybrid",
        candidates=tuple(
            RankedDocument(document=document, score=1, sources=("bm25",)) for document in documents
        ),
        estimated_tokens=20,
        catalog_hash=catalog.catalog_hash,
    )
    context = SchemaContext(
        db_id="synthetic",
        selected_tables=["order_items", "products"],
        selected_columns=["order_items.price", "products.category"],
        joins=["order_items.product_id = products.product_id"],
        evidence=[],
        catalog_hash=catalog.catalog_hash,
    )
    decomposition = DecomposedQuestion(
        question_language="en",
        metric_hints=["revenue"],
        dimension_hints=["category"],
        rationale="test fixture",
    )
    links = build_semantic_link_plan(
        "Revenue by category", decomposition, retrieval, context, catalog
    )
    assert {(link.role, link.table, link.column) for link in links.links} == {
        (SemanticRole.METRIC, "order_items", "price"),
        (SemanticRole.DIMENSION, "products", "category"),
    }
    assert links.required_tables == ("order_items", "products")
    assert all(link.evidence_id.startswith("synthetic.") for link in links.links)


def test_linker_keeps_compact_connected_component_covering_metric_and_dimension() -> None:
    catalog = SQLiteIntrospector().inspect(
        ROOT / "data/samples/synthetic_commerce_tiny.sqlite", "synthetic"
    )
    documents = (
        CatalogDocument(
            document_id="synthetic.order_items.price",
            db_id="synthetic",
            kind="column",
            table="order_items",
            column="price",
            description="revenue measure",
            catalog_hash=catalog.catalog_hash,
        ),
        CatalogDocument(
            document_id="synthetic.products.category",
            db_id="synthetic",
            kind="column",
            table="products",
            column="category",
            description="category dimension",
            catalog_hash=catalog.catalog_hash,
        ),
    )
    retrieval = RetrievalResult(
        db_id="synthetic",
        mode="hybrid",
        candidates=tuple(
            RankedDocument(document=document, score=1, sources=("bm25",)) for document in documents
        ),
        estimated_tokens=20,
        catalog_hash=catalog.catalog_hash,
    )
    plan = LogicalPlan(
        question_language="en",
        task_type="ranking",
        metrics=["revenue"],
        dimensions=["category"],
        required_concepts=["revenue", "category"],
    )
    context = link_schema(plan, retrieval, catalog)
    assert context.selected_tables == ["order_items", "products"]
    assert context.joins == ["order_items.product_id = products.product_id"]


def test_unique_lookup_relation_closes_multi_hop_translation_path() -> None:
    catalog = CatalogSnapshot(
        db_id="commerce",
        catalog_hash="1" * 64,
        tables=(
            TableInfo(
                name="items",
                columns=(ColumnInfo(name="product_id", data_type="TEXT"),),
                foreign_keys=(
                    ForeignKeyInfo(
                        from_columns=("product_id",),
                        target_table="products",
                        target_columns=("product_id",),
                    ),
                ),
            ),
            TableInfo(
                name="products",
                columns=(
                    ColumnInfo(name="product_id", data_type="TEXT", primary_key_position=1),
                    ColumnInfo(name="category_name", data_type="TEXT"),
                ),
            ),
            TableInfo(
                name="category_translation",
                columns=(
                    ColumnInfo(name="category_name", data_type="TEXT", primary_key_position=1),
                    ColumnInfo(name="english_name", data_type="TEXT"),
                ),
            ),
        ),
    )
    tables, joins = minimal_join_closure(catalog, ["items", "category_translation"], 2)
    assert tables == {"items", "products", "category_translation"}
    assert joins == [
        "items.product_id = products.product_id",
        "products.category_name = category_translation.category_name",
    ]


def test_direct_count_uses_exact_base_entity_as_population_owner() -> None:
    catalog = SQLiteIntrospector().inspect(
        ROOT / "data/samples/synthetic_commerce_tiny.sqlite", "synthetic"
    )
    documents = (
        CatalogDocument(
            document_id="synthetic.products",
            db_id="synthetic",
            kind="table",
            table="products",
            description="table products",
            catalog_hash=catalog.catalog_hash,
        ),
        CatalogDocument(
            document_id="synthetic.products.category",
            db_id="synthetic",
            kind="column",
            table="products",
            column="category",
            description="product category",
            catalog_hash=catalog.catalog_hash,
        ),
    )
    retrieval = RetrievalResult(
        db_id="synthetic",
        mode="hybrid",
        candidates=tuple(
            RankedDocument(document=document, score=1, sources=("bm25",)) for document in documents
        ),
        estimated_tokens=10,
        catalog_hash=catalog.catalog_hash,
    )
    context = SchemaContext(
        db_id="synthetic",
        selected_tables=["products"],
        selected_columns=["products.category"],
        joins=[],
        evidence=[],
        catalog_hash=catalog.catalog_hash,
    )
    decomposition = DecomposedQuestion(
        question_language="en",
        entity_hints=["products"],
        dimension_hints=["category"],
        rationale="test fixture",
    )
    links = build_semantic_link_plan(
        "How many products lack a category?",
        decomposition,
        retrieval,
        context,
        catalog,
    )
    assert links.population_owner == "products"
    assert links.required_tables == ("products",)
