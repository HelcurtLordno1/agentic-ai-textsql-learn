"""Layer 1 planning contracts."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RouteIntent(StrEnum):
    QUERY = "QUERY"
    CLARIFY = "CLARIFY"
    UNSUPPORTED = "UNSUPPORTED"
    WRITE_REQUEST = "WRITE_REQUEST"


class RouteDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    intent: RouteIntent
    reason: str


class DecomposedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_language: Literal["vi", "en", "other"]
    metric_hints: list[str] = Field(default_factory=list)
    dimension_hints: list[str] = Field(default_factory=list)
    filter_hints: list[str] = Field(default_factory=list)
    sort_hints: list[str] = Field(default_factory=list)
    limit_hint: int | None = Field(default=None, ge=1)
    time_hints: list[str] = Field(default_factory=list)
    set_operation_hint: str | None = None
    rationale: str = Field(max_length=500)


class LogicalPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_language: Literal["vi", "en", "other"]
    task_type: Literal["lookup", "aggregation", "ranking", "comparison", "set"]
    metrics: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    sort: list[str] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1)
    required_concepts: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
