"""Cross-layer budget and trace contracts."""

from pydantic import BaseModel, ConfigDict, Field


class QueryBudget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    max_llm_calls: int = Field(default=5, ge=0)
    max_candidates: int = Field(default=3, ge=1)
    max_repairs: int = Field(default=2, ge=0)
    run_deadline_seconds: int = Field(default=60, ge=1)


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    layer: str
    event: str
    elapsed_ms: float = Field(ge=0)
    details: dict[str, str] = Field(default_factory=dict)
