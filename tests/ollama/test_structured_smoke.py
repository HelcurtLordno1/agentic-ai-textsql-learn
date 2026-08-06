import os

import pytest
from pydantic import BaseModel, ConfigDict, Field

from agentic_text2sql.adapters.llm.ollama_provider import OllamaProvider


class LiveSmokeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: str
    sql: str = Field(pattern=r"(?is)^\s*select\b")
    read_only: bool


@pytest.mark.ollama
@pytest.mark.skipif(os.getenv("TEXT2SQL_RUN_OLLAMA_TESTS") != "1", reason="explicit live test")
def test_live_qwen_structured_vietnamese_sql() -> None:
    with OllamaProvider() as provider:
        result = provider.generate_structured(
            prompt=(
                "Trả JSON đúng schema: language='vi', read_only=true, và SQLite SQL SELECT 1 "
                "AS ket_qua. Không markdown."
            ),
            response_model=LiveSmokeResponse,
        )
    assert result.language == "vi"
    assert result.read_only is True
    assert "select" in result.sql.lower()
