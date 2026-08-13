"""Typed, gold-blind contracts for bounded guided correction."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from agentic_text2sql.contracts.validation import ErrorClass, ValidationReport


class StopReason(StrEnum):
    VALID = "VALID"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    MAX_REPAIRS = "MAX_REPAIRS"
    CALL_BUDGET = "CALL_BUDGET"
    DEADLINE = "DEADLINE"
    REPEATED_SQL = "REPEATED_SQL"
    REPEATED_ERROR = "REPEATED_ERROR"
    MODEL_ERROR = "MODEL_ERROR"


class CorrectionPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    error_class: ErrorClass
    suspected_cause: str = Field(min_length=1, max_length=500)
    changes_required: tuple[str, ...] = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()
    should_retry: bool


class AttemptSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    attempt: int = Field(ge=0)
    sql_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation: ValidationReport
    elapsed_ms: float = Field(ge=0)


class CorrectionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempted: bool
    recovered: bool
    stop_reason: StopReason
    repairs: int = Field(ge=0)
    llm_calls: int = Field(ge=0)
    trigger_error_class: ErrorClass | None = None
    attempts: list[AttemptSummary] = Field(default_factory=list)
