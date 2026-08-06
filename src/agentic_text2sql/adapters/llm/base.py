"""Port implemented by structured local language-model providers."""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class StructuredLLM(Protocol):
    def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type[StructuredModel],
        model: str | None = None,
    ) -> StructuredModel:
        """Generate and validate one structured response."""
        ...
