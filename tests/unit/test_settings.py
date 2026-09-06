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
    assert settings.planning_mode == "din_sql"


def test_planning_mode_is_bounded_to_reproducible_ablation_variants() -> None:
    assert Settings(TEXT2SQL_PLANNING_MODE="baseline").planning_mode == "baseline"
    with pytest.raises(ValidationError):
        Settings(TEXT2SQL_PLANNING_MODE="experimental-untracked")
