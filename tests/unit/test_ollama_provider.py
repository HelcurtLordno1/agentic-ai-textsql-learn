import json

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, Field

from agentic_text2sql.adapters.llm.ollama_provider import OllamaProvider
from agentic_text2sql.exceptions import ProviderUnavailableError, StructuredOutputError
from agentic_text2sql.settings import Settings


def test_model_metadata_survives_server_parameter_map_order_changes() -> None:
    parameters = iter(
        [
            'top_k 20\nstop "<|im_start|>"\nstop "<|im_end|>"\ntemperature 0.6',
            'temperature     0.6\nstop "<|im_end|>"\nstop "<|im_start|>"\ntop_k 20',
            'temperature 0.7\nstop "<|im_end|>"\nstop "<|im_start|>"\ntop_k 20',
        ]
    )

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/show"
        return httpx.Response(
            200, json={"template": "fixed template", "parameters": next(parameters)}
        )

    provider = make_provider(httpx.MockTransport(respond))
    first = provider.model_metadata("local:model")
    assert provider.model_metadata("local:model") == first
    changed = provider.model_metadata("local:model")
    assert changed["parameters_sha256"] != first["parameters_sha256"]
    assert changed["template_sha256"] == first["template_sha256"]


def test_parameter_normalization_keeps_repeated_scalar_order_and_stop_duplicates() -> None:
    from agentic_text2sql.adapters.llm.ollama_provider import canonical_model_parameters

    assert canonical_model_parameters("temperature 0.6\ntemperature 0.7") != (
        canonical_model_parameters("temperature 0.7\ntemperature 0.6")
    )
    assert canonical_model_parameters('stop "x"\nstop "x"') != canonical_model_parameters(
        'stop "x"'
    )
    with pytest.raises(ProviderUnavailableError, match="malformed parameter metadata"):
        canonical_model_parameters("temperature")


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: str = Field(pattern=r"(?is)^\s*select\b")
    read_only: bool


def make_provider(handler: httpx.MockTransport) -> OllamaProvider:
    settings = Settings(
        OLLAMA_BASE_URL="http://ollama.test",
        TEXT2SQL_OLLAMA_MODEL="local:model",
        TEXT2SQL_OLLAMA_NUM_GPU=0,
        TEXT2SQL_GUARDED_RUN=True,
    )
    client = httpx.Client(transport=handler, base_url=settings.ollama_base_url)
    return OllamaProvider(settings, client=client)


def test_structured_generation_sends_json_schema_and_validates() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "local:model"
        assert body["think"] is False
        assert body["options"]["seed"] == 42
        assert body["format"]["additionalProperties"] is False
        assert "pattern" not in body["format"]["properties"]["sql"]
        return httpx.Response(
            200,
            json={
                "message": {"content": '{"sql":"SELECT 1","read_only":true}'},
                "total_duration": 8_000_000,
                "load_duration": 2_000_000,
                "prompt_eval_duration": 3_000_000,
                "eval_duration": 3_000_000,
                "prompt_eval_count": 40,
                "eval_count": 10,
            },
        )

    provider = make_provider(httpx.MockTransport(respond))
    answer = provider.generate_structured(prompt="query", response_model=Answer)
    assert answer == Answer(sql="SELECT 1", read_only=True)
    assert provider.telemetry.milliseconds() == {
        "llm_total": 8.0,
        "llm_load": 2.0,
        "llm_prompt_eval": 3.0,
        "llm_eval": 3.0,
        "llm_calls": 1.0,
        "llm_prompt_tokens": 40.0,
        "llm_output_tokens": 10.0,
    }


def test_malformed_output_retries_once_then_raises() -> None:
    attempts = 0

    def respond(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, json={"message": {"content": "not-json"}})

    provider = make_provider(httpx.MockTransport(respond))
    with pytest.raises(StructuredOutputError, match="after 2 attempt"):
        provider.generate_structured(prompt="query", response_model=Answer)
    assert attempts == 2


def test_transport_errors_are_sanitized() -> None:
    def fail(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret-bearing raw transport detail")

    provider = make_provider(httpx.MockTransport(fail))
    with pytest.raises(ProviderUnavailableError) as caught:
        provider.version()
    assert "secret-bearing" not in str(caught.value)
