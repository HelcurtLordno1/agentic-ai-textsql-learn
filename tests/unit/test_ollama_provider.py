import json

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, Field

from agentic_text2sql.adapters.llm.ollama_provider import OllamaProvider
from agentic_text2sql.exceptions import ProviderUnavailableError, StructuredOutputError
from agentic_text2sql.settings import Settings


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: str = Field(pattern=r"(?is)^\s*select\b")
    read_only: bool


def make_provider(handler: httpx.MockTransport) -> OllamaProvider:
    settings = Settings(OLLAMA_BASE_URL="http://ollama.test", TEXT2SQL_OLLAMA_MODEL="local:model")
    client = httpx.Client(transport=handler, base_url=settings.ollama_base_url)
    return OllamaProvider(settings, client=client)


def test_structured_generation_sends_json_schema_and_validates() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "local:model"
        assert body["think"] is False
        assert body["format"]["additionalProperties"] is False
        assert "pattern" not in body["format"]["properties"]["sql"]
        return httpx.Response(
            200,
            json={"message": {"content": '{"sql":"SELECT 1","read_only":true}'}},
        )

    provider = make_provider(httpx.MockTransport(respond))
    answer = provider.generate_structured(prompt="query", response_model=Answer)
    assert answer == Answer(sql="SELECT 1", read_only=True)


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
