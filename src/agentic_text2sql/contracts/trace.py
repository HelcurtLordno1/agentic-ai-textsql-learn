"""Cross-layer budget, persistence, and trace contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class QueryBudget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    max_llm_calls: int = Field(default=5, ge=0)
    max_candidates: int = Field(default=3, ge=1)
    max_repairs: int = Field(default=2, ge=0)
    run_deadline_seconds: int = Field(default=60, ge=1)


class TraceEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: str
    layer: str
    event: str
    elapsed_ms: float = Field(ge=0)
    details: dict[str, str] = Field(default_factory=dict)
    sequence: int = Field(default=0, ge=0)
    created_at: str | None = None


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RunRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: str
    db_id: str
    question: str
    status: RunStatus
    created_at: str
    updated_at: str
    config: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None


class FeedbackRating(StrEnum):
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"


class FeedbackCategory(StrEnum):
    WRONG_RESULT = "WRONG_RESULT"
    WRONG_SHAPE = "WRONG_SHAPE"
    WRONG_METRIC = "WRONG_METRIC"
    WRONG_FILTER = "WRONG_FILTER"
    WRONG_JOIN = "WRONG_JOIN"
    MISSING_DATA = "MISSING_DATA"
    TOO_SLOW = "TOO_SLOW"
    UNSAFE_OR_UNEXPECTED = "UNSAFE_OR_UNEXPECTED"
    OTHER = "OTHER"


class FeedbackRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    feedback_id: str
    run_id: str
    rating: FeedbackRating
    categories: tuple[FeedbackCategory, ...] = ()
    note: str | None = Field(default=None, max_length=2000)
    created_at: str
