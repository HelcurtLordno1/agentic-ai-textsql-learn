"""Database-scoped BM25, dense, and hybrid retrieval."""

import time
from collections.abc import Callable
from typing import Literal, cast

from agentic_text2sql.contracts.retrieval import CatalogDocument, RankedDocument, RetrievalResult
from agentic_text2sql.layer2_grounding.context_packer import estimate_tokens
from agentic_text2sql.layer2_grounding.embedding_index import DenseIndex
from agentic_text2sql.layer2_grounding.keyword_index import KeywordIndex
from agentic_text2sql.layer2_grounding.rank_fusion import reciprocal_rank_fusion


class HybridRetriever:
    def __init__(
        self,
        db_id: str,
        catalog_hash: str,
        documents: tuple[CatalogDocument, ...],
        keyword: KeywordIndex,
        dense: DenseIndex,
        embed_query: Callable[[str], list[float]],
    ) -> None:
        if any(document.db_id != db_id for document in documents):
            raise ValueError("cross-database document detected while loading index")
        self.db_id = db_id
        self.catalog_hash = catalog_hash
        self.documents = documents
        self.keyword = keyword
        self.dense = dense
        self.embed_query = embed_query

    def retrieve(
        self, query: str, mode: str = "hybrid", top_k: int = 12, token_budget: int = 1200
    ) -> RetrievalResult:
        if mode not in {"bm25", "dense", "hybrid"}:
            raise ValueError("mode must be bm25, dense, or hybrid")
        fetch_k = min(len(self.documents), max(top_k * 3, top_k))
        started = time.perf_counter()
        bm25 = self.keyword.search(query, fetch_k) if mode != "dense" else []
        keyword_ms = (time.perf_counter() - started) * 1000
        embedding_ms = 0.0
        dense_started = time.perf_counter()
        dense = []
        if mode != "bm25":
            embedding_started = time.perf_counter()
            vector = self.embed_query(query)
            embedding_ms = (time.perf_counter() - embedding_started) * 1000
            dense_started = time.perf_counter()
            dense = self.dense.search(vector, fetch_k)
        dense_lookup_ms = (time.perf_counter() - dense_started) * 1000 if dense else 0.0
        if mode == "hybrid":
            ranking = reciprocal_rank_fusion(
                {"bm25": bm25, "dense": dense}, {"bm25": 1.0, "dense": 1.0}
            )
        else:
            source = mode
            raw = bm25 if mode == "bm25" else dense
            ranking = [(index, score, (source,)) for index, score in raw]
        candidates = [
            RankedDocument(document=self.documents[index], score=max(0.0, score), sources=sources)
            for index, score, sources in ranking[:top_k]
            if self.documents[index].db_id == self.db_id
        ]
        del token_budget  # Enforced on the fully rendered SchemaContext by the linker.
        return RetrievalResult(
            db_id=self.db_id,
            mode=cast(Literal["bm25", "dense", "hybrid"], mode),
            candidates=tuple(candidates),
            estimated_tokens=sum(
                estimate_tokens(candidate.document.retrieval_text()) for candidate in candidates
            ),
            catalog_hash=self.catalog_hash,
            latency_ms={
                "query_embedding": embedding_ms,
                "keyword_lookup": keyword_ms,
                "dense_lookup": dense_lookup_ms,
                "total": (time.perf_counter() - started) * 1000,
            },
        )
