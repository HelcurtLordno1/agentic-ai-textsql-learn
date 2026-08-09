"""Typed contracts shared by the Layer 2 grounding components."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    evidence_id: str
    kind: str
    table: str
    column: str | None = None
    score: float = Field(ge=0)


class CatalogDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    document_id: str
    db_id: str
    kind: Literal["table", "column", "relationship"]
    table: str
    column: str | None = None
    data_type: str | None = None
    description: str
    neighbors: tuple[str, ...] = ()
    catalog_hash: str

    def retrieval_text(self) -> str:
        identifiers = " ".join(
            part for part in (self.table, self.column, *self.neighbors) if part is not None
        )
        return f"{identifiers} {self.description}".strip()


class RankedDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    document: CatalogDocument
    score: float = Field(ge=0)
    sources: tuple[str, ...]


class RetrievalResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    db_id: str
    mode: Literal["bm25", "dense", "hybrid"]
    candidates: tuple[RankedDocument, ...]
    estimated_tokens: int = Field(ge=0)
    catalog_hash: str
    latency_ms: dict[str, float] = Field(default_factory=dict)


class IndexManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: int = 2
    version_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    db_id: str
    catalog_hash: str
    model_id: str
    model_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_template: str
    document_count: int = Field(gt=0)
    embedding_dimension: int = Field(gt=0)
    files: dict[str, str]
    cold_build_seconds: float = Field(ge=0)


class SchemaContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    db_id: str
    selected_tables: list[str]
    selected_columns: list[str]
    joins: list[str]
    evidence: list[EvidenceItem]
    catalog_hash: str
    rendered_context: str = ""
    estimated_tokens: int = Field(default=0, ge=0)
