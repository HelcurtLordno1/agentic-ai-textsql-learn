"""Layer 4 validation contracts."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorClass(StrEnum):
    SYNTAX_ERROR = "SYNTAX_ERROR"
    UNKNOWN_TABLE = "UNKNOWN_TABLE"
    UNKNOWN_COLUMN = "UNKNOWN_COLUMN"
    AMBIGUOUS_COLUMN = "AMBIGUOUS_COLUMN"
    TYPE_OR_FUNCTION_ERROR = "TYPE_OR_FUNCTION_ERROR"
    JOIN_ERROR = "JOIN_ERROR"
    FILTER_OR_VALUE_ERROR = "FILTER_OR_VALUE_ERROR"
    AGGREGATION_ERROR = "AGGREGATION_ERROR"
    DIALECT_ERROR = "DIALECT_ERROR"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    TIMEOUT = "TIMEOUT"
    EMPTY_RESULT_SUSPECTED = "EMPTY_RESULT_SUSPECTED"
    UNKNOWN_RUNTIME_ERROR = "UNKNOWN_RUNTIME_ERROR"


class ResultPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool = False
    elapsed_ms: float = Field(default=0, ge=0)


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: bool
    error_class: ErrorClass | None = None
    safe_message: str | None = None
    warnings: list[str] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    allowed: bool
    normalized_sql: str | None = None
    error_class: ErrorClass | None = None
    safe_message: str | None = None
    limit_injected: bool = False
