"""Strict public API schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentic_text2sql.contracts.trace import FeedbackCategory, FeedbackRating, RunStatus


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    db_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=2000)
    correction_enabled: bool = False


class QueryAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    status: RunStatus
    events_url: str


class QueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    db_id: str
    question: str
    status: RunStatus
    created_at: str
    updated_at: str
    config: dict[str, Any]
    result: dict[str, Any] | None = None


class CatalogIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset: Literal["olist", "synthetic_tiny"]


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    rating: FeedbackRating
    categories: tuple[FeedbackCategory, ...] = ()
    note: str | None = Field(default=None, max_length=2000)
