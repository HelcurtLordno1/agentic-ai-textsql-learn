"""Central, relocatable settings for local execution."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
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
    ollama_num_gpu: int | None = Field(default=None, alias="TEXT2SQL_OLLAMA_NUM_GPU", ge=0, le=64)
    ollama_num_batch: int = Field(default=64, alias="TEXT2SQL_OLLAMA_NUM_BATCH", ge=1, le=256)
    ollama_num_thread: int = Field(default=8, alias="TEXT2SQL_OLLAMA_NUM_THREAD", ge=1, le=32)
    gpu_execution_profile: Literal["qwen14b-gpu300-f16-b16"] | None = Field(
        default=None, alias="TEXT2SQL_GPU_EXECUTION_PROFILE"
    )
    monitor_windows_host: bool = Field(default=False, alias="TEXT2SQL_MONITOR_WINDOWS_HOST")
    pipeline_mode: Literal["p6", "a1"] = Field(default="p6", alias="TEXT2SQL_PIPELINE_MODE")
    critic_mode: Literal["off", "shadow", "repair"] = Field(
        default="off", alias="TEXT2SQL_CRITIC_MODE"
    )
    generation_format: Literal["json", "sql_text"] = Field(
        default="json", alias="TEXT2SQL_GENERATION_FORMAT"
    )
    generation_model_digest: str | None = Field(
        default=None, alias="TEXT2SQL_GENERATION_MODEL_DIGEST", pattern=r"^[0-9a-f]{64}$"
    )
    a1_max_requests: int = Field(default=3, alias="TEXT2SQL_A1_MAX_REQUESTS", ge=1, le=3)
    input_token_budget: int = Field(
        default=2800, alias="TEXT2SQL_INPUT_TOKEN_BUDGET", ge=256, le=2800
    )
    output_token_budget: int = Field(
        default=768, alias="TEXT2SQL_OUTPUT_TOKEN_BUDGET", ge=64, le=2048
    )
    guarded_run: bool = Field(default=False, alias="TEXT2SQL_GUARDED_RUN")
    critic_shadow_sample_rate: float = Field(
        default=0, alias="TEXT2SQL_CRITIC_SHADOW_SAMPLE_RATE", ge=0, le=1
    )
    repair_feedback_mode: Literal["grounded", "generic"] = Field(
        default="grounded", alias="TEXT2SQL_REPAIR_FEEDBACK_MODE"
    )
    compute_policy: Literal["legacy", "obligation"] = Field(
        default="legacy", alias="TEXT2SQL_COMPUTE_POLICY"
    )
    deterministic_repair: bool = Field(default=False, alias="TEXT2SQL_DETERMINISTIC_REPAIR")
    recover_empty_relations: bool = Field(default=False, alias="TEXT2SQL_RECOVER_EMPTY_RELATIONS")
    resolve_derived_columns: bool = Field(default=False, alias="TEXT2SQL_RESOLVE_DERIVED_COLUMNS")
    bounded_output_contracts: bool = Field(default=False, alias="TEXT2SQL_BOUNDED_OUTPUT_CONTRACTS")
    owner_repair_feedback: bool = Field(default=False, alias="TEXT2SQL_OWNER_REPAIR_FEEDBACK")
    repairability_routing: bool = Field(default=True, alias="TEXT2SQL_REPAIRABILITY_ROUTING")
    ollama_seed: int = Field(default=42, alias="TEXT2SQL_OLLAMA_SEED", ge=0)
    request_timeout_seconds: float = Field(
        default=120.0, alias="TEXT2SQL_REQUEST_TIMEOUT_SECONDS", gt=0
    )
    run_deadline_seconds: float = Field(
        default=120.0, alias="TEXT2SQL_RUN_DEADLINE_SECONDS", ge=30, le=900
    )

    @model_validator(mode="after")
    def bound_context(self) -> Settings:
        approved_gpu = self.gpu_execution_profile == "qwen14b-gpu300-f16-b16"
        if approved_gpu and (
            self.ollama_num_gpu != 41
            or self.ollama_num_batch != 16
            or self.ollama_num_thread != 8
            or self.run_deadline_seconds != 900
            or self.request_timeout_seconds != 300
        ):
            raise ValueError("GPU300 settings must match the approved execution profile")
        if self.run_deadline_seconds > 180 and self.ollama_num_gpu != 0 and not approved_gpu:
            raise ValueError("Deadlines above 180 seconds require explicit CPU-only offload")
        if self.input_token_budget + self.output_token_budget + 256 > 4096:
            raise ValueError("Input/output budgets must reserve 256 tokens in the 4096 context")
        return self

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
