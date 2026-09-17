"""Central, relocatable settings for local execution."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def discover_project_root() -> Path:
    """Resolve the repository root without depending on the current directory."""
    return Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Environment-overridable paths and local provider configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_root: Path = Field(default_factory=discover_project_root, alias="PROJECT_ROOT")
    data_dir: Path | None = Field(default=None, alias="TEXT2SQL_DATA_DIR")
    artifact_dir: Path | None = Field(default=None, alias="TEXT2SQL_ARTIFACT_DIR")
    ollama_base_url: str = Field(default="http://127.0.0.1:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen3:14b-q4_K_M", alias="TEXT2SQL_OLLAMA_MODEL")
    ollama_num_gpu: int | None = Field(default=None, alias="TEXT2SQL_OLLAMA_NUM_GPU", ge=0)
    ollama_seed: int = Field(default=42, alias="TEXT2SQL_OLLAMA_SEED", ge=0)
    ollama_max_output_tokens: int = Field(
        default=1024, alias="TEXT2SQL_OLLAMA_MAX_OUTPUT_TOKENS", ge=128, le=2048
    )
    request_timeout_seconds: float = Field(
        default=120.0, alias="TEXT2SQL_REQUEST_TIMEOUT_SECONDS", gt=0
    )
    run_deadline_seconds: float = Field(
        default=120.0, alias="TEXT2SQL_RUN_DEADLINE_SECONDS", ge=30, le=180
    )
    planning_mode: Literal["baseline", "hybrid", "din_sql"] = Field(
        default="baseline", alias="TEXT2SQL_PLANNING_MODE"
    )
    candidate_mode: Literal["legacy", "shadow", "enforce"] = Field(
        default="legacy", alias="TEXT2SQL_CANDIDATE_MODE"
    )
    candidate_total_deadline_seconds: float = Field(
        default=300.0,
        alias="TEXT2SQL_CANDIDATE_TOTAL_DEADLINE_SECONDS",
        ge=60,
        le=600,
    )
    candidate_minimum_challenger_seconds: float = Field(
        default=45.0,
        alias="TEXT2SQL_CANDIDATE_MINIMUM_CHALLENGER_SECONDS",
        ge=10,
        le=300,
    )
    certified_proof_kinds: str = Field(default="", alias="TEXT2SQL_CERTIFIED_PROOF_KINDS")
    retrieval_mode: Literal["bm25", "dense", "hybrid"] = Field(
        default="hybrid", alias="TEXT2SQL_RETRIEVAL_MODE"
    )

    @field_validator("ollama_base_url")
    @classmethod
    def normalize_ollama_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            normalized = f"http://{normalized}"
        return normalized

    @property
    def parsed_certified_proof_kinds(self) -> frozenset[str]:
        allowed = {
            "frequency_ranking",
            "aggregate:count_rows",
            "aggregate:count_distinct",
            "aggregate:sum",
            "aggregate:avg",
            "aggregate:min",
            "aggregate:max",
        }
        values = frozenset(
            item.strip().casefold()
            for item in self.certified_proof_kinds.split(",")
            if item.strip()
        )
        unknown = values - allowed
        if unknown:
            raise ValueError(f"unknown certified proof kinds: {', '.join(sorted(unknown))}")
        return values

    @property
    def resolved_data_dir(self) -> Path:
        return (self.data_dir or self.project_root / "data").resolve()

    @property
    def resolved_artifact_dir(self) -> Path:
        return (self.artifact_dir or self.resolved_data_dir / "artifacts").resolve()
