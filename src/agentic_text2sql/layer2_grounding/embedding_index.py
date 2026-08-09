"""Normalized FAISS cosine index and deterministic on-disk serialization."""

from __future__ import annotations

from pathlib import Path

import faiss
import numpy as np
from numpy.typing import NDArray


def normalized_matrix(vectors: list[list[float]]) -> NDArray[np.float32]:
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError("embedding matrix must be non-empty and two-dimensional")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("zero-length embedding is not indexable")
    return matrix / norms


class DenseIndex:
    def __init__(self, matrix: NDArray[np.float32]) -> None:
        self.dimension = int(matrix.shape[1])
        self._index: faiss.Index = faiss.IndexFlatIP(self.dimension)
        self._index.add(matrix)

    @classmethod
    def build(cls, vectors: list[list[float]]) -> DenseIndex:
        return cls(normalized_matrix(vectors))

    @classmethod
    def load(cls, path: Path) -> DenseIndex:
        instance = cls.__new__(cls)
        instance._index = faiss.read_index(str(path))
        instance.dimension = int(instance._index.d)
        return instance

    def save(self, path: Path) -> None:
        faiss.write_index(self._index, str(path))

    def search(self, vector: list[float], top_k: int) -> list[tuple[int, float]]:
        query = normalized_matrix([vector])
        scores, indices = self._index.search(query, min(top_k, self._index.ntotal))
        return [
            (int(index), max(0.0, float(score)))
            for index, score in zip(indices[0], scores[0], strict=True)
            if index >= 0
        ]
