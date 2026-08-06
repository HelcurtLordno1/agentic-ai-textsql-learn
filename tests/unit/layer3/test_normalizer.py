import pytest

from agentic_text2sql.contracts.sql import SqlCandidate
from agentic_text2sql.layer3_generation.normalizer import CandidateNormalizer
from agentic_text2sql.layer4_validation.parser import SQLParseError


def candidate(sql: str) -> SqlCandidate:
    return SqlCandidate(sql=sql, confidence=0.8)


def test_normalizer_removes_fence_semicolon_and_fingerprints() -> None:
    normalizer = CandidateNormalizer()
    first = normalizer.normalize(
        candidate("```sql\nSELECT 1;\n```"),
        model_name="local",
        prompt_version="generator_v1",
        catalog_hash="a" * 64,
    )
    second = normalizer.normalize(
        candidate("SELECT 1"),
        model_name="local",
        prompt_version="generator_v1",
        catalog_hash="a" * 64,
    )
    assert first.normalized_sql == "SELECT 1"
    assert first.fingerprint == second.fingerprint


@pytest.mark.parametrize("sql", ["SELECT 1; SELECT 2", "not sql", ""])
def test_normalizer_rejects_invalid_or_multiple_statements(sql: str) -> None:
    with pytest.raises((SQLParseError, ValueError)):
        CandidateNormalizer().normalize(
            candidate(sql),
            model_name="local",
            prompt_version="generator_v1",
            catalog_hash="a" * 64,
        )
