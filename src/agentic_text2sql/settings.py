"""Central, relocatable settings for local execution."""

from __future__ import annotations

from pathlib import Path

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
    request_timeout_seconds: float = Field(
        default=120.0, alias="TEXT2SQL_REQUEST_TIMEOUT_SECONDS", gt=0
    )

    @field_validator("ollama_base_url")
    @classmethod
    def normalize_ollama_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            normalized = f"http://{normalized}"
        return normalized

    @property
    def resolved_data_dir(self) -> Path:
        return (self.data_dir or self.project_root / "data").resolve()

    @property
    def resolved_artifact_dir(self) -> Path:
        return (self.artifact_dir or self.resolved_data_dir / "artifacts").resolve()
