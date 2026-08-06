"""Layer 3 SQL candidate contracts."""

from pydantic import BaseModel, ConfigDict, Field


class SqlCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: str = Field(min_length=1)
    used_tables: list[str] = Field(default_factory=list)
    used_columns: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
