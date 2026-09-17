"""Layer 3 SQL candidate and direct-baseline contracts."""

from enum import StrEnum
from typing import Any, Literal

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
    prompt_estimated_tokens: int = Field(default=0, ge=0)


class DirectStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    CLARIFY = "CLARIFY"
    UNSUPPORTED = "UNSUPPORTED"
    WRITE_BLOCKED = "WRITE_BLOCKED"
    MODEL_ERROR = "MODEL_ERROR"
    GROUNDING_ERROR = "GROUNDING_ERROR"
    INVALID_SQL = "INVALID_SQL"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    VALIDATION_FAILED = "VALIDATION_FAILED"


class CandidateSelection(StrEnum):
    KEEP_INCUMBENT = "KEEP_INCUMBENT"
    PROMOTE_CHALLENGER = "PROMOTE_CHALLENGER"
    SKIP_CHALLENGER = "SKIP_CHALLENGER"


class CandidateArbitration(BaseModel):
    """Gold-blind decision between one frozen incumbent and one specialist challenger."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    mode: Literal["shadow", "enforce"]
    selection: CandidateSelection
    reason: str
    incumbent_status: DirectStatus
    challenger_status: DirectStatus | None = None
    incumbent_fingerprint: str | None = None
    challenger_fingerprint: str | None = None
    incumbent_candidate: CandidateRecord | None = None
    incumbent_result_columns: list[str] = Field(default_factory=list)
    incumbent_result_rows: list[list[Any]] = Field(default_factory=list)
    challenger_candidate: CandidateRecord | None = None
    challenger_result_columns: list[str] = Field(default_factory=list)
    challenger_result_rows: list[list[Any]] = Field(default_factory=list)
    challenger_rule_ids: tuple[str, ...] = ()
    challenger_proof_kind: str | None = None
    challenger_proof_accepted: bool = False
    incumbent_contradictions: tuple[str, ...] = ()
    challenger_contradictions: tuple[str, ...] = ()
    elapsed_ms: float = Field(ge=0)


class DirectRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    question: str
    status: DirectStatus
    route_reason: str
    prompt_versions: dict[str, str]
    adaptive_route: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None
    plan_validation: dict[str, Any] | None = None
    schema_context: dict[str, Any] | None = None
    candidate: CandidateRecord | None = None
    result_columns: list[str] = Field(default_factory=list)
    result_rows: list[list[Any]] = Field(default_factory=list)
    error_class: str | None = None
    safe_message: str | None = None
    latency_ms: dict[str, float] = Field(default_factory=dict)
    correction: dict[str, Any] | None = None
    arbitration: CandidateArbitration | None = None
