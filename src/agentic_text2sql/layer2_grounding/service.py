"""Build and load verified Layer 2 index bundles."""

from __future__ import annotations

import hashlib
import json
import pickle
import shutil
import time
from collections.abc import Callable
from pathlib import Path

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.retrieval import CatalogDocument
from agentic_text2sql.layer2_grounding.document_builder import build_documents
from agentic_text2sql.layer2_grounding.embedding_index import DenseIndex
from agentic_text2sql.layer2_grounding.keyword_index import KeywordIndex
from agentic_text2sql.layer2_grounding.retriever import HybridRetriever

DOCUMENT_TEMPLATE_VERSION = "p3-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class IndexService:
    def __init__(
        self, root: Path, model_id: str, embed_many: Callable[[list[str]], list[list[float]]]
    ) -> None:
        self.root = root
        self.model_id = model_id
        self.embed_many = embed_many

    def build(
        self, catalog: CatalogSnapshot, aliases: dict[str, str] | None = None
    ) -> dict[str, object]:
        started = time.perf_counter()
        documents = build_documents(catalog, aliases)
        bundle = self.root / catalog.db_id
        temporary = self.root / f".{catalog.db_id}.building"
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir(parents=True)
        (temporary / "catalog.json").write_text(catalog.model_dump_json(indent=2), encoding="utf-8")
        self._write_jsonl(temporary / "documents.jsonl", documents)
        self._write_jsonl(
            temporary / "tables.jsonl", tuple(d for d in documents if d.kind == "table")
        )
        self._write_jsonl(
            temporary / "columns.jsonl", tuple(d for d in documents if d.kind == "column")
        )
        self._write_jsonl(
            temporary / "relationships.jsonl",
            tuple(d for d in documents if d.kind == "relationship"),
        )
        vectors = self._cached_embeddings(documents)
        DenseIndex.build(vectors).save(temporary / "faiss.index")
        with (temporary / "bm25.pkl").open("wb") as stream:
            pickle.dump(KeywordIndex(documents), stream, protocol=5)
        files = [
            "catalog.json",
            "documents.jsonl",
            "tables.jsonl",
            "columns.jsonl",
            "relationships.jsonl",
            "faiss.index",
            "bm25.pkl",
        ]
        manifest: dict[str, object] = {
            "version": 1,
            "db_id": catalog.db_id,
            "catalog_hash": catalog.catalog_hash,
            "model_id": self.model_id,
            "document_template": DOCUMENT_TEMPLATE_VERSION,
            "document_count": len(documents),
            "files": {name: _sha256(temporary / name) for name in files},
            "build_seconds": round(time.perf_counter() - started, 6),
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        if bundle.exists():
            shutil.rmtree(bundle)
        temporary.rename(bundle)
        return manifest

    def is_current(self, catalog: CatalogSnapshot) -> bool:
        manifest_path = self.root / catalog.db_id / "manifest.json"
        if not manifest_path.exists():
            return False
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return bool(
            manifest.get("catalog_hash") == catalog.catalog_hash
            and manifest.get("model_id") == self.model_id
            and manifest.get("document_template") == DOCUMENT_TEMPLATE_VERSION
        )

    def load(self, db_id: str, embed_query: Callable[[str], list[float]]) -> HybridRetriever:
        bundle = self.root / db_id
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        for name, expected in manifest["files"].items():
            if _sha256(bundle / name) != expected:
                raise ValueError(f"index artifact checksum mismatch: {name}")
        documents = tuple(
            CatalogDocument.model_validate_json(line)
            for line in (bundle / "documents.jsonl").read_text(encoding="utf-8").splitlines()
        )
        with (bundle / "bm25.pkl").open("rb") as stream:
            keyword = pickle.load(stream)
        if not isinstance(keyword, KeywordIndex):
            raise ValueError("invalid keyword index artifact")
        return HybridRetriever(
            db_id,
            str(manifest["catalog_hash"]),
            documents,
            keyword,
            DenseIndex.load(bundle / "faiss.index"),
            embed_query,
        )

    @staticmethod
    def _write_jsonl(path: Path, documents: tuple[CatalogDocument, ...]) -> None:
        path.write_text(
            "".join(document.model_dump_json() + "\n" for document in documents), encoding="utf-8"
        )

    def _cached_embeddings(self, documents: tuple[CatalogDocument, ...]) -> list[list[float]]:
        cache_path = self.root / "_embedding_cache.json"
        cache: dict[str, list[float]] = (
            json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        )
        keys = [
            hashlib.sha256(
                f"{self.model_id}\0{DOCUMENT_TEMPLATE_VERSION}\0{doc.retrieval_text()}".encode()
            ).hexdigest()
            for doc in documents
        ]
        missing = [position for position, key in enumerate(keys) if key not in cache]
        if missing:
            texts = [documents[position].retrieval_text() for position in missing]
            generated = self.embed_many(texts)
            if len(generated) != len(texts):
                raise ValueError("embedding provider returned an unexpected vector count")
            for position, vector in zip(missing, generated, strict=True):
                cache[keys[position]] = vector
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(cache, sort_keys=True), encoding="utf-8")
            temporary.replace(cache_path)
        return [cache[key] for key in keys]
