"""Layer 2 schema-grounding contracts."""

from pydantic import BaseModel, ConfigDict, Field


class EvidenceItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    evidence_id: str
    kind: str
    table: str
    column: str | None = None
    score: float = Field(ge=0)


class SchemaContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    db_id: str
    selected_tables: list[str]
    selected_columns: list[str]
    joins: list[str]
    evidence: list[EvidenceItem]
    catalog_hash: str
