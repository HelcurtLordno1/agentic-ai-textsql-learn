"""BM25 index with identifier-aware tokenization and exact boosts."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Any

from agentic_text2sql.contracts.retrieval import CatalogDocument

_TOKEN = re.compile(r"[\w]+", re.UNICODE)


def normalize_tokens(text: str) -> list[str]:
    lowered = text.casefold()
    folded = "".join(
        c for c in unicodedata.normalize("NFKD", lowered) if not unicodedata.combining(c)
    )
    originals = _TOKEN.findall(lowered)
    expanded = [piece for token in originals for piece in token.split("_") if piece]
    folded_tokens = _TOKEN.findall(folded)
    return originals + expanded + [token for token in folded_tokens if token not in originals]


class KeywordIndex:
    def __init__(self, documents: tuple[CatalogDocument, ...]) -> None:
        self.documents = documents
        self.tokens = [normalize_tokens(doc.retrieval_text()) for doc in documents]
        self._df = Counter(token for row in self.tokens for token in set(row))
        self._average_length = sum(map(len, self.tokens)) / max(1, len(self.tokens))

    def search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        query_tokens = normalize_tokens(query)
        scores: list[tuple[int, float]] = []
        total = len(self.documents)
        for index, row in enumerate(self.tokens):
            counts = Counter(row)
            score = 0.0
            for token in query_tokens:
                frequency = counts[token]
                if not frequency:
                    continue
                inverse = math.log(1 + (total - self._df[token] + 0.5) / (self._df[token] + 0.5))
                denominator = frequency + 1.5 * (1 - 0.75 + 0.75 * len(row) / self._average_length)
                score += inverse * frequency * 2.5 / denominator
            identifiers = {self.documents[index].table.casefold()}
            column = self.documents[index].column
            if column:
                identifiers.add(column.casefold())
            score += 4.0 * sum(identifier in query.casefold() for identifier in identifiers)
            if score > 0:
                scores.append((index, score))
        return sorted(scores, key=lambda item: (-item[1], self.documents[item[0]].document_id))[
            :top_k
        ]

    def artifact_payload(self) -> dict[str, Any]:
        return {
            "version": 1,
            "document_ids": [document.document_id for document in self.documents],
            "tokens": self.tokens,
            "parameters": {"k1": 1.5, "b": 0.75, "exact_identifier_boost": 4.0},
        }

    def validate_payload(self, payload: object) -> None:
        if not isinstance(payload, dict) or payload != self.artifact_payload():
            raise ValueError("keyword index artifact does not match catalog documents")
