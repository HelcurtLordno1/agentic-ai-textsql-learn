from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.retrieval import CatalogDocument
from agentic_text2sql.layer2_grounding.context_packer import pack_candidates
from agentic_text2sql.layer2_grounding.document_builder import build_documents
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer2_grounding.keyword_index import normalize_tokens
from agentic_text2sql.layer2_grounding.service import IndexService
from agentic_text2sql_eval.schema_metrics import extract_gold_schema


def fake_vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    return [float(value) for value in digest[:16]]


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
    service = IndexService(tmp_path, "fake-v1", lambda texts: [fake_vector(t) for t in texts])
    first = service.build(catalog)
    assert service.is_current(catalog)
    retriever = service.load(catalog.db_id, fake_vector)
    result = retriever.retrieve("orders customers", top_k=6, token_budget=80)
    assert result.db_id == catalog.db_id
    assert result.estimated_tokens <= 80
    assert all(item.document.db_id == catalog.db_id for item in result.candidates)
    second = service.build(catalog)
    assert first["catalog_hash"] == second["catalog_hash"]
    assert first["files"] == second["files"]


def test_checksum_and_cross_database_are_rejected(tmp_path: Path) -> None:
    catalog = fixture_catalog()
    service = IndexService(tmp_path, "fake-v1", lambda texts: [fake_vector(t) for t in texts])
    service.build(catalog)
    documents = tmp_path / catalog.db_id / "documents.jsonl"
    documents.write_text(documents.read_text() + "{}\n")
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
    gold = extract_gold_schema(
        "SELECT o.id FROM orders AS o JOIN customers AS c ON o.customer_id = c.id"
    )
    assert gold.tables == {"orders", "customers"}
    assert gold.foreign_keys == {frozenset({"orders.customer_id", "customers.id"})}
