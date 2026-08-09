"""Build and load immutable, checksum-verified Layer 2 index bundles."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.retrieval import (
    CatalogDocument,
    IndexManifest,
    SchemaContext,
)
from agentic_text2sql.layer2_grounding.document_builder import build_documents
from agentic_text2sql.layer2_grounding.embedding_index import DenseIndex
from agentic_text2sql.layer2_grounding.keyword_index import KeywordIndex
from agentic_text2sql.layer2_grounding.retriever import HybridRetriever
from agentic_text2sql.layer2_grounding.schema_linker import link_schema

DOCUMENT_TEMPLATE_VERSION = "p3.1-v2"
INDEX_FILES = frozenset(
    {
        "catalog.json",
        "documents.jsonl",
        "tables.jsonl",
        "columns.jsonl",
        "relationships.jsonl",
        "faiss.index",
        "bm25.json",
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"index build already in progress: {path.parent.name}") from exc
    os.close(descriptor)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


class IndexService:
    def __init__(
        self,
        root: Path,
        model_id: str,
        model_digest: str,
        embed_many: Callable[[list[str]], list[list[float]]],
    ) -> None:
        if re.fullmatch(r"[0-9a-f]{64}", model_digest) is None:
            raise ValueError("model_digest must be a 64-character Ollama digest")
        self.root = root
        self.model_id = model_id
        self.model_digest = model_digest
        self.embed_many = embed_many

    def build(
        self, catalog: CatalogSnapshot, aliases: dict[str, str] | None = None
    ) -> IndexManifest:
        started = time.perf_counter()
        documents = build_documents(catalog, aliases)
        version_id = self._version_id(catalog, documents)
        database_root = self.root / catalog.db_id
        version_root = database_root / "versions" / version_id
        with _exclusive_lock(database_root / ".build.lock"):
            if not version_root.exists():
                self._build_version(version_root, catalog, documents, version_id, started)
            self._activate(database_root, version_id)
        return self._read_manifest(version_root)

    def is_current(self, catalog: CatalogSnapshot) -> bool:
        try:
            version_root = self._active_version_root(catalog.db_id)
            manifest = self._read_manifest(version_root)
            self._validate_bundle(version_root, manifest)
        except (FileNotFoundError, KeyError, ValueError):
            return False
        return bool(
            manifest.catalog_hash == catalog.catalog_hash
            and manifest.model_id == self.model_id
            and manifest.model_digest == self.model_digest
            and manifest.document_template == DOCUMENT_TEMPLATE_VERSION
        )

    def load(self, db_id: str, embed_query: Callable[[str], list[float]]) -> HybridRetriever:
        version_root = self._active_version_root(db_id)
        manifest = self._read_manifest(version_root)
        self._validate_bundle(version_root, manifest)
        if (
            manifest.db_id != db_id
            or manifest.model_id != self.model_id
            or manifest.model_digest != self.model_digest
            or manifest.document_template != DOCUMENT_TEMPLATE_VERSION
        ):
            raise ValueError("active index identity does not match the requested runtime")
        documents = tuple(
            CatalogDocument.model_validate_json(line)
            for line in (version_root / "documents.jsonl").read_text(encoding="utf-8").splitlines()
        )
        if len(documents) != manifest.document_count:
            raise ValueError("document count does not match index manifest")
        if any(
            document.db_id != db_id or document.catalog_hash != manifest.catalog_hash
            for document in documents
        ):
            raise ValueError("cross-database or stale catalog document detected")
        keyword = KeywordIndex(documents)
        keyword.validate_payload(
            json.loads((version_root / "bm25.json").read_text(encoding="utf-8"))
        )
        dense = DenseIndex.load(version_root / "faiss.index")
        if (
            dense.count != manifest.document_count
            or dense.dimension != manifest.embedding_dimension
        ):
            raise ValueError("FAISS shape does not match index manifest")
        return HybridRetriever(db_id, manifest.catalog_hash, documents, keyword, dense, embed_query)

    def _build_version(
        self,
        version_root: Path,
        catalog: CatalogSnapshot,
        documents: tuple[CatalogDocument, ...],
        version_id: str,
        started: float,
    ) -> None:
        temporary = version_root.with_name(f".{version_root.name}.building")
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir(parents=True)
        try:
            (temporary / "catalog.json").write_text(
                catalog.model_dump_json(indent=2), encoding="utf-8"
            )
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
            dense = DenseIndex.build(vectors)
            dense.save(temporary / "faiss.index")
            keyword = KeywordIndex(documents)
            (temporary / "bm25.json").write_text(
                json.dumps(keyword.artifact_payload(), ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            files = tuple(sorted(INDEX_FILES))
            manifest = IndexManifest(
                version_id=version_id,
                db_id=catalog.db_id,
                catalog_hash=catalog.catalog_hash,
                model_id=self.model_id,
                model_digest=self.model_digest,
                document_template=DOCUMENT_TEMPLATE_VERSION,
                document_count=len(documents),
                embedding_dimension=dense.dimension,
                files={name: _sha256(temporary / name) for name in files},
                cold_build_seconds=round(time.perf_counter() - started, 6),
            )
            (temporary / "manifest.json").write_text(
                manifest.model_dump_json(indent=2), encoding="utf-8"
            )
            version_root.parent.mkdir(parents=True, exist_ok=True)
            temporary.rename(version_root)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    @staticmethod
    def _activate(database_root: Path, version_id: str) -> None:
        pointer = database_root / "active.json"
        temporary = database_root / ".active.tmp"
        temporary.write_text(json.dumps({"version_id": version_id}), encoding="utf-8")
        os.replace(temporary, pointer)

    def _active_version_root(self, db_id: str) -> Path:
        database_root = self.root / db_id
        payload = json.loads((database_root / "active.json").read_text(encoding="utf-8"))
        version_id = payload["version_id"]
        if not isinstance(version_id, str) or re.fullmatch(r"[0-9a-f]{16}", version_id) is None:
            raise ValueError("invalid active index pointer")
        return database_root / "versions" / version_id

    @staticmethod
    def _read_manifest(version_root: Path) -> IndexManifest:
        return IndexManifest.model_validate_json(
            (version_root / "manifest.json").read_text(encoding="utf-8")
        )

    @staticmethod
    def _validate_bundle(version_root: Path, manifest: IndexManifest) -> None:
        if set(manifest.files) != INDEX_FILES:
            raise ValueError("index manifest has missing or unexpected artifacts")
        for name, expected in manifest.files.items():
            if _sha256(version_root / name) != expected:
                raise ValueError(f"index artifact checksum mismatch: {name}")

    def _version_id(self, catalog: CatalogSnapshot, documents: tuple[CatalogDocument, ...]) -> str:
        identity = json.dumps(
            {
                "catalog_hash": catalog.catalog_hash,
                "model_id": self.model_id,
                "model_digest": self.model_digest,
                "template": DOCUMENT_TEMPLATE_VERSION,
                "documents": [document.model_dump(mode="json") for document in documents],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(identity.encode()).hexdigest()[:16]

    @staticmethod
    def _write_jsonl(path: Path, documents: tuple[CatalogDocument, ...]) -> None:
        path.write_text(
            "".join(document.model_dump_json() + "\n" for document in documents), encoding="utf-8"
        )

    def _cached_embeddings(self, documents: tuple[CatalogDocument, ...]) -> list[list[float]]:
        cache_path = self.root / "embedding_cache.sqlite"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(cache_path, timeout=30)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS embeddings "
                "(cache_key TEXT PRIMARY KEY, vector_json TEXT NOT NULL)"
            )
            keys = [
                hashlib.sha256(
                    f"{self.model_digest}\0{DOCUMENT_TEMPLATE_VERSION}\0{doc.retrieval_text()}".encode()
                ).hexdigest()
                for doc in documents
            ]
            cached: dict[str, list[float]] = {}
            for offset in range(0, len(keys), 500):
                chunk = keys[offset : offset + 500]
                placeholders = ",".join("?" for _ in chunk)
                cached.update(
                    {
                        key: json.loads(value)
                        for key, value in connection.execute(
                            "SELECT cache_key, vector_json FROM embeddings "
                            f"WHERE cache_key IN ({placeholders})",
                            chunk,
                        )
                    }
                )
            missing = [position for position, key in enumerate(keys) if key not in cached]
            if missing:
                generated = self.embed_many(
                    [documents[position].retrieval_text() for position in missing]
                )
                if len(generated) != len(missing):
                    raise ValueError("embedding provider returned an unexpected vector count")
                for position, vector in zip(missing, generated, strict=True):
                    cached[keys[position]] = vector
                    connection.execute(
                        "INSERT OR REPLACE INTO embeddings(cache_key, vector_json) VALUES (?, ?)",
                        (keys[position], json.dumps(vector, separators=(",", ":"))),
                    )
                connection.commit()
            vectors = [[float(value) for value in cached[key]] for key in keys]
            if not vectors or any(len(vector) != len(vectors[0]) for vector in vectors):
                raise ValueError("embedding cache contains inconsistent dimensions")
            return vectors
        finally:
            connection.close()


class GroundingService:
    """Question/plan facade used by the generation workflow without gold access."""

    def __init__(
        self,
        retriever: HybridRetriever,
        catalog: CatalogSnapshot,
        *,
        mode: str = "dense",
        top_k: int = 20,
        token_budget: int = 1200,
    ) -> None:
        self.retriever = retriever
        self.catalog = catalog
        self.mode = mode
        self.top_k = top_k
        self.token_budget = token_budget

    def ground(self, question: str, plan: LogicalPlan) -> SchemaContext:
        expanded_query = " ".join(
            [
                question,
                *plan.metrics,
                *plan.dimensions,
                *plan.filters,
                *plan.required_concepts,
            ]
        )
        retrieval = self.retriever.retrieve(expanded_query, mode=self.mode, top_k=self.top_k)
        return link_schema(plan, retrieval, self.catalog, token_budget=self.token_budget)
