from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import httpx
import pytest

from agentic_text2sql.adapters.embeddings.ollama_embeddings import OllamaEmbeddingClient
from agentic_text2sql.contracts.catalog import (
    CatalogSnapshot,
    ColumnInfo,
    ForeignKeyInfo,
    TableInfo,
)
from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.retrieval import (
    CatalogDocument,
    RankedDocument,
    RetrievalResult,
)
from agentic_text2sql.layer2_grounding.context_packer import pack_candidates
from agentic_text2sql.layer2_grounding.document_builder import build_documents
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer2_grounding.keyword_index import normalize_tokens
from agentic_text2sql.layer2_grounding.rank_fusion import reciprocal_rank_fusion
from agentic_text2sql.layer2_grounding.service import IndexService
from agentic_text2sql_eval.schema_metrics import extract_gold_schema, score_retrieval
from agentic_text2sql_eval.spider_adapter import create_manifest


def fake_vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    return [float(value) for value in digest[:16]]


MODEL_DIGEST = "a" * 64


def index_service(path: Path) -> IndexService:
    return IndexService(
        path, "fake-v1", MODEL_DIGEST, lambda texts: [fake_vector(t) for t in texts]
    )


def fixture_catalog() -> CatalogSnapshot:
    return SQLiteIntrospector().inspect(
        Path("data/samples/synthetic_commerce_tiny.sqlite"), "synthetic"
    )


def test_catalog_and_documents_are_stable() -> None:
    first = fixture_catalog()
    second = fixture_catalog()
    assert first.catalog_hash == second.catalog_hash
    assert build_documents(first) == build_documents(second)
    assert any(document.kind == "relationship" for document in build_documents(first))


def test_identifier_and_vietnamese_normalization() -> None:
    tokens = normalize_tokens("Tổng phí olist_order_items")
    assert {"tong", "phi", "olist_order_items", "order", "items"} <= set(tokens)


def test_index_build_reload_and_budget(tmp_path: Path) -> None:
    catalog = fixture_catalog()
    service = index_service(tmp_path)
    first = service.build(catalog)
    assert service.is_current(catalog)
    retriever = service.load(catalog.db_id, fake_vector)
    result = retriever.retrieve("orders customers", top_k=6)
    assert result.db_id == catalog.db_id
    assert result.estimated_tokens > 0
    assert all(item.document.db_id == catalog.db_id for item in result.candidates)
    second = service.build(catalog)
    assert first.catalog_hash == second.catalog_hash
    assert first.files == second.files
    assert first.version_id == second.version_id


def test_checksum_and_cross_database_are_rejected(tmp_path: Path) -> None:
    catalog = fixture_catalog()
    service = index_service(tmp_path)
    service.build(catalog)
    active = json.loads((tmp_path / catalog.db_id / "active.json").read_text(encoding="utf-8"))
    documents = tmp_path / catalog.db_id / "versions" / active["version_id"] / "documents.jsonl"
    documents.write_text(documents.read_text() + "{}\n")
    assert not service.is_current(catalog)
    with pytest.raises(ValueError, match="checksum"):
        service.load(catalog.db_id, fake_vector)
    foreign = CatalogDocument(
        document_id="other.x",
        db_id="other",
        kind="table",
        table="x",
        description="x",
        catalog_hash=catalog.catalog_hash,
    )
    from agentic_text2sql.layer2_grounding.embedding_index import DenseIndex
    from agentic_text2sql.layer2_grounding.keyword_index import KeywordIndex
    from agentic_text2sql.layer2_grounding.retriever import HybridRetriever

    with pytest.raises(ValueError, match="cross-database"):
        HybridRetriever(
            catalog.db_id,
            catalog.catalog_hash,
            (foreign,),
            KeywordIndex((foreign,)),
            DenseIndex.build([fake_vector("x")]),
            fake_vector,
        )


def test_packer_rejects_invalid_budget() -> None:
    with pytest.raises(ValueError, match="positive"):
        pack_candidates([], 0)


def test_gold_schema_extracts_alias_resolved_join_offline() -> None:
    catalog = fixture_catalog()
    tables = {table.name for table in catalog.tables}
    assert {"orders", "customers"} <= tables
    gold = extract_gold_schema(
        "SELECT o.order_id FROM orders AS o JOIN customers AS c ON o.customer_id = c.customer_id",
        catalog,
    )
    assert gold.tables == {"orders", "customers"}
    assert gold.columns >= {
        "orders.order_id",
        "orders.customer_id",
        "customers.customer_id",
    }
    assert gold.foreign_keys == {frozenset({"orders.customer_id", "customers.customer_id"})}


def test_plan_aware_linker_enforces_final_budget(tmp_path: Path) -> None:
    from agentic_text2sql.layer2_grounding.schema_linker import link_schema

    catalog = fixture_catalog()
    service = index_service(tmp_path)
    service.build(catalog)
    retrieval = service.load(catalog.db_id, fake_vector).retrieve(
        "orders customers", mode="dense", top_k=10
    )
    plan = LogicalPlan(
        question_language="en",
        task_type="aggregation",
        metrics=["order count"],
        required_concepts=["customers"],
    )
    context = link_schema(plan, retrieval, catalog, token_budget=120)
    assert context.estimated_tokens <= 120
    assert context.rendered_context
    assert set(context.selected_columns) >= {
        side.strip()
        for join in context.joins
        for equality in join.split(" AND ")
        for side in equality.split(" = ")
    }


def test_join_closure_drops_disconnected_schema_decoys() -> None:
    from agentic_text2sql.layer2_grounding.fk_graph import minimal_join_closure

    catalog = CatalogSnapshot(
        db_id="coherent",
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
                columns=(ColumnInfo(name="product_id", data_type="TEXT"),),
            ),
            TableInfo(
                name="order_totals",
                kind="view",
                columns=(ColumnInfo(name="revenue", data_type="INTEGER"),),
            ),
        ),
        catalog_hash="coherent-catalog",
    )

    tables, joins = minimal_join_closure(catalog, ["items", "order_totals", "products"], max_hops=2)

    assert tables == {"items", "products"}
    assert joins == ["items.product_id = products.product_id"]

    reversed_tables, reversed_joins = minimal_join_closure(
        catalog, ["order_totals", "items", "products"], max_hops=2
    )
    assert reversed_tables == {"items", "products"}
    assert reversed_joins == ["items.product_id = products.product_id"]


def test_schema_linker_prefers_compact_semantic_view_for_scalar_intent() -> None:
    from agentic_text2sql.layer2_grounding.schema_linker import link_schema

    catalog = CatalogSnapshot(
        db_id="olist",
        tables=(
            TableInfo(
                name="customer_order_facts",
                kind="view",
                columns=(
                    ColumnInfo(name="customer_unique_id", data_type="TEXT"),
                    ColumnInfo(name="order_count", data_type="INTEGER"),
                ),
            ),
            TableInfo(
                name="customers",
                columns=(
                    ColumnInfo(name="customer_id", data_type="TEXT"),
                    ColumnInfo(name="customer_unique_id", data_type="TEXT"),
                ),
            ),
            TableInfo(
                name="orders",
                columns=(
                    ColumnInfo(name="order_id", data_type="TEXT"),
                    ColumnInfo(name="customer_id", data_type="TEXT"),
                ),
                foreign_keys=(
                    ForeignKeyInfo(
                        from_columns=("customer_id",),
                        target_table="customers",
                        target_columns=("customer_id",),
                    ),
                ),
            ),
            TableInfo(
                name="items",
                columns=(
                    ColumnInfo(name="product_id", data_type="TEXT"),
                    ColumnInfo(name="freight_cents", data_type="INTEGER"),
                    ColumnInfo(name="price_cents", data_type="INTEGER"),
                ),
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
                    ColumnInfo(name="product_id", data_type="TEXT"),
                    ColumnInfo(name="category", data_type="TEXT"),
                ),
            ),
            TableInfo(
                name="order_totals",
                kind="view",
                columns=(
                    ColumnInfo(name="revenue_cents", data_type="INTEGER"),
                    ColumnInfo(name="freight_cents", data_type="INTEGER"),
                ),
            ),
            TableInfo(
                name="category_translation",
                columns=(ColumnInfo(name="category", data_type="TEXT"),),
            ),
        ),
        catalog_hash="semantic-catalog",
    )

    def ranked(
        document_id: str,
        kind: Literal["table", "column", "relationship"],
        table: str,
        column: str | None,
        score: float,
        neighbors: tuple[str, ...] = (),
    ) -> RankedDocument:
        return RankedDocument(
            document=CatalogDocument(
                document_id=document_id,
                db_id="olist",
                kind=kind,
                table=table,
                column=column,
                description=document_id,
                neighbors=neighbors,
                catalog_hash=catalog.catalog_hash,
            ),
            score=score,
            sources=("hybrid",),
        )

    retrieval = RetrievalResult(
        db_id="olist",
        mode="hybrid",
        candidates=(
            ranked(
                "olist.customer_order_facts.customer_unique_id",
                "column",
                "customer_order_facts",
                "customer_unique_id",
                1.0,
            ),
            ranked(
                "olist.customers.customer_unique_id",
                "column",
                "customers",
                "customer_unique_id",
                0.99,
            ),
            ranked(
                "olist.customer_order_facts.order_count",
                "column",
                "customer_order_facts",
                "order_count",
                0.98,
            ),
            ranked(
                "olist.orders.fk0",
                "relationship",
                "orders",
                None,
                0.97,
                ("orders.customer_id = customers.customer_id",),
            ),
        ),
        estimated_tokens=40,
        catalog_hash=catalog.catalog_hash,
    )
    plan = LogicalPlan(
        question_language="vi",
        task_type="aggregation",
        metrics=["returning customer count"],
        required_concepts=["customer_unique_id", "returning customers"],
    )

    context = link_schema(plan, retrieval, catalog)

    assert context.selected_tables == ["customer_order_facts"]
    assert "customer_order_facts.order_count" in context.selected_columns

    revenue_retrieval = RetrievalResult(
        db_id="olist",
        mode="hybrid",
        candidates=(
            ranked(
                "olist.category_translation.category",
                "column",
                "category_translation",
                "category",
                1.0,
            ),
            ranked(
                "olist.order_totals.revenue_cents", "column", "order_totals", "revenue_cents", 0.99
            ),
            ranked("olist.items.freight_cents", "column", "items", "freight_cents", 0.98),
            ranked("olist.products.category", "column", "products", "category", 0.97),
            ranked(
                "olist.items.fk0",
                "relationship",
                "items",
                None,
                0.96,
                ("items.product_id = products.product_id",),
            ),
        ),
        estimated_tokens=50,
        catalog_hash=catalog.catalog_hash,
    )
    revenue_plan = LogicalPlan(
        question_language="vi",
        task_type="ranking",
        metrics=["revenue", "freight"],
        dimensions=["category"],
        limit=5,
        required_concepts=["revenue", "freight", "category"],
    )

    revenue_context = link_schema(revenue_plan, revenue_retrieval, catalog)

    assert revenue_context.selected_tables == ["items", "products"]
    assert "items.product_id = products.product_id" in revenue_context.joins


def test_failed_rebuild_keeps_previous_active_bundle(tmp_path: Path) -> None:
    catalog = fixture_catalog()
    service = index_service(tmp_path)
    first = service.build(catalog)

    def fail(_: list[str]) -> list[list[float]]:
        raise RuntimeError("provider unavailable")

    failing = IndexService(tmp_path, "fake-v1", MODEL_DIGEST, fail)
    with pytest.raises(RuntimeError, match="provider unavailable"):
        failing.build(catalog, {"orders": "changed description"})
    active = json.loads((tmp_path / catalog.db_id / "active.json").read_text(encoding="utf-8"))
    assert active["version_id"] == first.version_id
    assert service.load(catalog.db_id, fake_vector).db_id == catalog.db_id


def test_load_rejects_different_model_digest(tmp_path: Path) -> None:
    catalog = fixture_catalog()
    index_service(tmp_path).build(catalog)
    wrong_model = IndexService(
        tmp_path,
        "fake-v1",
        "b" * 64,
        lambda texts: [fake_vector(text) for text in texts],
    )
    with pytest.raises(ValueError, match="identity"):
        wrong_model.load(catalog.db_id, fake_vector)


def test_plan_terms_change_single_table_selection() -> None:
    from agentic_text2sql.layer2_grounding.schema_linker import link_schema

    catalog = fixture_catalog()
    documents = (
        CatalogDocument(
            document_id="synthetic.customers",
            db_id="synthetic",
            kind="table",
            table="customers",
            description="customer table",
            catalog_hash=catalog.catalog_hash,
        ),
        CatalogDocument(
            document_id="synthetic.products",
            db_id="synthetic",
            kind="table",
            table="products",
            description="product catalog",
            catalog_hash=catalog.catalog_hash,
        ),
    )
    retrieval = RetrievalResult(
        db_id="synthetic",
        mode="dense",
        candidates=tuple(
            RankedDocument(document=document, score=0.5, sources=("dense",))
            for document in documents
        ),
        estimated_tokens=10,
        catalog_hash=catalog.catalog_hash,
    )
    plan = LogicalPlan(
        question_language="en",
        task_type="lookup",
        required_concepts=["product catalog"],
    )
    context = link_schema(plan, retrieval, catalog, max_tables=1)
    assert context.selected_tables == ["products"]


def test_qualified_metric_rejects_same_name_from_wrong_table() -> None:
    catalog = fixture_catalog()
    gold = extract_gold_schema("SELECT customer_id FROM customers", catalog)
    wrong = CatalogDocument(
        document_id="synthetic.orders.customer_id",
        db_id="synthetic",
        kind="column",
        table="orders",
        column="customer_id",
        description="wrong table same column name",
        catalog_hash=catalog.catalog_hash,
    )
    retrieval = RetrievalResult(
        db_id="synthetic",
        mode="dense",
        candidates=(RankedDocument(document=wrong, score=1.0, sources=("dense",)),),
        estimated_tokens=10,
        catalog_hash=catalog.catalog_hash,
    )
    assert score_retrieval(retrieval, gold)["column_recall"] == 0.0


def test_spider_manifest_has_exactly_100_unique_rows(tmp_path: Path) -> None:
    cases = [
        {
            "db_id": f"db_{index // 5:02d}",
            "question": f"question {index}",
            "query": f"SELECT value FROM table_{index // 5}",
        }
        for index in range(100)
    ]
    dev = tmp_path / "dev.json"
    dev.write_text(json.dumps(cases), encoding="utf-8")
    manifest = create_manifest(dev)
    assert len(manifest.cases) == 100
    assert len({case.dev_index for case in manifest.cases}) == 100


def test_rrf_preserves_both_sources_and_stable_order() -> None:
    fused = reciprocal_rank_fusion({"bm25": [(1, 4.0), (0, 2.0)], "dense": [(0, 0.9)]})
    assert fused[0][0] == 0
    assert fused[0][2] == ("bm25", "dense")


def test_ollama_embedding_model_digest() -> None:
    digest = "b" * 64

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "bge-m3:latest", "digest": digest}]})

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    )
    client = OllamaEmbeddingClient("http://ollama.test", "bge-m3:latest", client=http_client)
    try:
        assert client.model_digest() == digest
    finally:
        client.close()


def test_ollama_embedding_telemetry_is_observed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        assert json.loads(request.content)["options"] == {"num_gpu": 0}
        return httpx.Response(
            200,
            json={
                "embeddings": [[0.1, 0.2]],
                "total_duration": 7_000_000,
                "load_duration": 2_000_000,
                "prompt_eval_count": 3,
            },
        )

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    )
    client = OllamaEmbeddingClient("http://ollama.test", "bge-m3:latest", client=http_client)
    try:
        assert client.embed(["orders"]) == [[0.1, 0.2]]
        assert client.telemetry == {
            "embedding_total": 7.0,
            "embedding_load": 2.0,
            "embedding_prompt_tokens": 3,
            "embedding_calls": 1,
        }
    finally:
        client.close()
