"""Layer 1 planning contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
