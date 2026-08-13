"""Small Ollama adapter with schema-constrained, validated output."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from agentic_text2sql.exceptions import ProviderUnavailableError, StructuredOutputError
from agentic_text2sql.settings import Settings

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


@dataclass
class OllamaTelemetry:
    calls: int = 0
    total_duration_ns: int = 0
    load_duration_ns: int = 0
    prompt_eval_duration_ns: int = 0
    eval_duration_ns: int = 0
    prompt_eval_count: int = 0
    eval_count: int = 0

    def observe(self, payload: dict[str, Any]) -> None:
        self.calls += 1
        for field in (
            "total_duration_ns",
            "load_duration_ns",
            "prompt_eval_duration_ns",
            "eval_duration_ns",
            "prompt_eval_count",
            "eval_count",
        ):
            source = field.removesuffix("_ns")
            value = payload.get(source)
            if isinstance(value, int) and value >= 0:
                setattr(self, field, getattr(self, field) + value)

    def milliseconds(self) -> dict[str, float]:
        return {
            "llm_total": self.total_duration_ns / 1_000_000,
            "llm_load": self.load_duration_ns / 1_000_000,
            "llm_prompt_eval": self.prompt_eval_duration_ns / 1_000_000,
            "llm_eval": self.eval_duration_ns / 1_000_000,
            "llm_calls": float(self.calls),
            "llm_prompt_tokens": float(self.prompt_eval_count),
            "llm_output_tokens": float(self.eval_count),
        }


def _ollama_compatible_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove validation-only keywords unsupported by Ollama's grammar compiler.

    Pydantic still validates the full model after generation, so removing a grammar keyword does
    not weaken the application contract. In particular, llama.cpp rejects Python inline regex
    flags such as ``(?is)`` even though they are valid Pydantic patterns.
    """
    unsupported = {"pattern"}
    return {
        key: (
            _ollama_compatible_schema(value)
            if isinstance(value, dict)
            else [
                _ollama_compatible_schema(item) if isinstance(item, dict) else item
                for item in value
            ]
            if isinstance(value, list)
            else value
        )
        for key, value in schema.items()
        if key not in unsupported
    }


class OllamaProvider:
    """Use Ollama's local chat API without any paid-provider dependency."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
        *,
        malformed_retries: int = 1,
    ) -> None:
        self.settings = settings or Settings()
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self.settings.ollama_base_url,
            timeout=self.settings.request_timeout_seconds,
        )
        self.malformed_retries = malformed_retries
        self.telemetry = OllamaTelemetry()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OllamaProvider:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def list_models(self) -> list[dict[str, Any]]:
        payload = self._request_json("GET", "/api/tags")
        models = payload.get("models")
        if not isinstance(models, list):
            raise ProviderUnavailableError("Ollama returned an invalid model-list response")
        return [item for item in models if isinstance(item, dict)]

    def version(self) -> str:
        payload = self._request_json("GET", "/api/version")
        version = payload.get("version")
        if not isinstance(version, str):
            raise ProviderUnavailableError("Ollama returned an invalid version response")
        return version

    def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type[StructuredModel],
        model: str | None = None,
    ) -> StructuredModel:
        chosen_model = model or self.settings.ollama_model
        validation_error: Exception | None = None
        for attempt in range(self.malformed_retries + 1):
            messages = [{"role": "user", "content": prompt}]
            if attempt:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "The previous response was invalid. "
                            "Return only JSON matching the schema."
                        ),
                    }
                )
            options = {"temperature": 0, "num_ctx": 4096}
            if self.settings.ollama_num_gpu is not None:
                options["num_gpu"] = self.settings.ollama_num_gpu
            payload = self._request_json(
                "POST",
                "/api/chat",
                json={
                    "model": chosen_model,
                    "messages": messages,
                    "stream": False,
                    "think": False,
                    "format": _ollama_compatible_schema(response_model.model_json_schema()),
                    "options": options,
                },
            )
            self.telemetry.observe(payload)
            try:
                content = payload["message"]["content"]
                if not isinstance(content, str):
                    raise TypeError("message content is not a string")
                return response_model.model_validate_json(content)
            except (KeyError, TypeError, ValidationError, ValueError, json.JSONDecodeError) as exc:
                validation_error = exc
        raise StructuredOutputError(
            "Ollama failed the structured-output contract after "
            f"{self.malformed_retries + 1} attempt(s)"
        ) from validation_error

    def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, **kwargs)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError(f"Ollama request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise ProviderUnavailableError("Ollama returned a non-object JSON response")
        return payload
