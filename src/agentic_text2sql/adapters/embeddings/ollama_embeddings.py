"""Bounded Ollama embedding client using the local HTTP API only."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx


class OllamaEmbeddingClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout_seconds
        )

    def embed(self, texts: Sequence[str], batch_size: int = 32) -> list[list[float]]:
        if not 1 <= batch_size <= 128:
            raise ValueError("batch_size must be between 1 and 128")
        vectors: list[list[float]] = []
        for offset in range(0, len(texts), batch_size):
            response = self._client.post(
                "/api/embed",
                json={"model": self.model, "input": list(texts[offset : offset + batch_size])},
            )
            response.raise_for_status()
            payload = response.json()
            batch = payload.get("embeddings")
            if not isinstance(batch, list) or not all(isinstance(row, list) for row in batch):
                raise ValueError("Ollama returned an invalid embeddings payload")
            vectors.extend([[float(value) for value in row] for row in batch])
        if len(vectors) != len(texts) or (
            vectors and any(len(v) != len(vectors[0]) for v in vectors)
        ):
            raise ValueError("Ollama returned an inconsistent embedding matrix")
        return vectors

    def model_digest(self) -> str:
        response = self._client.get("/api/tags")
        response.raise_for_status()
        payload: Any = response.json()
        models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            raise ValueError("Ollama returned an invalid model-list payload")
        for item in models:
            if isinstance(item, dict) and item.get("name") == self.model:
                digest = item.get("digest")
                if isinstance(digest, str) and len(digest) == 64:
                    return digest
        raise ValueError(f"Ollama model is not installed: {self.model}")

    def close(self) -> None:
        self._client.close()
