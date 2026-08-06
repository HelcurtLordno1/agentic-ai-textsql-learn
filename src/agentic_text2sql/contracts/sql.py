"""Layer 3 SQL candidate and direct-baseline contracts."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SqlCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: str = Field(min_length=1)
    used_tables: list[str] = Field(default_factory=list)
    used_columns: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class CandidateRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    candidate: SqlCandidate
    normalized_sql: str
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_name: str
    prompt_version: str
    catalog_hash: str


class DirectStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    CLARIFY = "CLARIFY"
    UNSUPPORTED = "UNSUPPORTED"
    WRITE_BLOCKED = "WRITE_BLOCKED"
    MODEL_ERROR = "MODEL_ERROR"
    INVALID_SQL = "INVALID_SQL"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    EXECUTION_ERROR = "EXECUTION_ERROR"


class DirectRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    question: str
    status: DirectStatus
    route_reason: str
    prompt_versions: dict[str, str]
    plan: dict[str, Any] | None = None
    candidate: CandidateRecord | None = None
    result_columns: list[str] = Field(default_factory=list)
    result_rows: list[list[Any]] = Field(default_factory=list)
    error_class: str | None = None
    safe_message: str | None = None
    latency_ms: dict[str, float] = Field(default_factory=dict)
