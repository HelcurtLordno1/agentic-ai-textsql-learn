from pathlib import Path

import pytest
from pydantic import ValidationError

from agentic_text2sql.settings import Settings


def test_settings_paths_are_relocatable(tmp_path: Path) -> None:
    settings = Settings(
        PROJECT_ROOT=tmp_path,
        TEXT2SQL_DATA_DIR=tmp_path / "external-data",
        OLLAMA_BASE_URL="example.test:11434/",
    )

    assert settings.resolved_data_dir == (tmp_path / "external-data").resolve()
    assert settings.resolved_artifact_dir == (tmp_path / "external-data/artifacts").resolve()
    assert settings.ollama_base_url == "http://example.test:11434"
    assert settings.ollama_seed == 42
    assert settings.ollama_max_output_tokens == 1024
    assert settings.planning_mode == "baseline"
    assert settings.candidate_mode == "legacy"
    assert settings.parsed_certified_proof_kinds == frozenset()
    assert settings.retrieval_mode == "hybrid"


def test_planning_mode_is_bounded_to_reproducible_ablation_variants() -> None:
    assert Settings(TEXT2SQL_PLANNING_MODE="baseline").planning_mode == "baseline"
    assert Settings(TEXT2SQL_PLANNING_MODE="hybrid").planning_mode == "hybrid"
    with pytest.raises(ValidationError):
        Settings(TEXT2SQL_PLANNING_MODE="experimental-untracked")


def test_retrieval_mode_is_bounded() -> None:
    assert Settings(TEXT2SQL_RETRIEVAL_MODE="bm25").retrieval_mode == "bm25"
    with pytest.raises(ValidationError):
        Settings(TEXT2SQL_RETRIEVAL_MODE="case-specific")


def test_candidate_modes_and_proof_kinds_are_bounded() -> None:
    settings = Settings(
        TEXT2SQL_CANDIDATE_MODE="enforce",
        TEXT2SQL_CERTIFIED_PROOF_KINDS="frequency_ranking,aggregate:max",
    )
    assert settings.candidate_mode == "enforce"
    assert settings.parsed_certified_proof_kinds == frozenset(
        {"frequency_ranking", "aggregate:max"}
    )
    with pytest.raises(ValidationError):
        Settings(TEXT2SQL_CANDIDATE_MODE="best-of-many")
    with pytest.raises(ValueError, match="unknown certified proof"):
        _ = Settings(TEXT2SQL_CERTIFIED_PROOF_KINDS="olist_acc_020").parsed_certified_proof_kinds
