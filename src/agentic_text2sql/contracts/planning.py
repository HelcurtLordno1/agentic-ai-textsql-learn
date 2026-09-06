"""Layer 1 planning contracts, including the typed DIN-SQL interfaces."""

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
    entity_hints: list[str] = Field(default_factory=list)
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


class SemanticRole(StrEnum):
    ENTITY = "ENTITY"
    METRIC = "METRIC"
    DIMENSION = "DIMENSION"
    FILTER = "FILTER"
    VALUE = "VALUE"


class SemanticLink(BaseModel):
    """One question mention grounded to catalog evidence, never benchmark gold."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    mention: str = Field(min_length=1, max_length=160)
    role: SemanticRole
    table: str
    column: str | None = None
    value: str | None = Field(default=None, max_length=160)
    evidence_id: str
    score: float = Field(ge=0)
    required: bool = False


class SemanticLinkPlan(BaseModel):
    """DIN-SQL schema links plus the bounded physical join closure."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    db_id: str
    catalog_hash: str
    links: tuple[SemanticLink, ...] = ()
    population_owner: str | None = None
    required_tables: tuple[str, ...] = ()
    join_paths: tuple[str, ...] = ()
    unmatched_mentions: tuple[str, ...] = ()


class ComplexityKind(StrEnum):
    SIMPLE = "SIMPLE"
    AGGREGATE = "AGGREGATE"
    MULTI_JOIN = "MULTI_JOIN"
    NESTED_SET_WINDOW = "NESTED_SET_WINDOW"


class PlanningStrategy(StrEnum):
    """The three adaptive generation classes used by DIN-SQL."""

    EASY = "EASY"
    NON_NESTED = "NON_NESTED"
    NESTED = "NESTED"


class ComplexityDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: ComplexityKind
    strategy: PlanningStrategy
    signals: tuple[str, ...] = Field(default=(), max_length=8)


class JoinStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left_table: str
    right_table: str
    condition: str
    purpose: str = Field(min_length=1, max_length=240)


class SubqueryStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    question: str = Field(min_length=1, max_length=300)
    output_grain: str = Field(min_length=1, max_length=160)
    select: list[str] = Field(min_length=1, max_length=12)
    from_tables: list[str] = Field(min_length=1, max_length=8)
    joins: list[JoinStep] = Field(default_factory=list, max_length=8)
    where: list[str] = Field(default_factory=list, max_length=12)
    group_by: list[str] = Field(default_factory=list, max_length=8)
    having: list[str] = Field(default_factory=list, max_length=8)
    depends_on: tuple[str, ...] = ()


class ClausePlan(BaseModel):
    """SQL-shaped intermediate representation without executable SQL."""

    model_config = ConfigDict(extra="forbid")
    select: list[str] = Field(min_length=1, max_length=12)
    from_tables: list[str] = Field(min_length=1, max_length=8)
    joins: list[JoinStep] = Field(default_factory=list, max_length=8)
    where: list[str] = Field(default_factory=list, max_length=12)
    group_by: list[str] = Field(default_factory=list, max_length=8)
    having: list[str] = Field(default_factory=list, max_length=8)
    order_by: list[str] = Field(default_factory=list, max_length=8)
    limit: int | None = Field(default=None, ge=1, le=1000)
    output_grain: str = Field(min_length=1, max_length=160)
    requires_distinct: bool = False
    subqueries: list[SubqueryStep] = Field(default_factory=list, max_length=6)
    set_operation: Literal["UNION", "INTERSECT", "EXCEPT"] | None = None


class DINSQLPlan(LogicalPlan):
    """Validated hand-off from semantic planning to SQL generation."""

    semantic_links: SemanticLinkPlan
    complexity: ComplexityDecision
    clauses: ClausePlan


class DINSQLDraft(LogicalPlan):
    """Model-produced portion; trusted schema links are attached by the runtime."""

    complexity: ComplexityDecision
    clauses: ClausePlan


class PlanValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    accepted: bool
    signals: tuple[str, ...] = ()
    safe_message: str | None = None
