"""Typed semantic intent, binding, and catalog contracts."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BindingStatus(StrEnum):
    PROVEN = "PROVEN"
    INCOMPLETE = "INCOMPLETE"
    AMBIGUOUS = "AMBIGUOUS"


class AggregateOperator(StrEnum):
    COUNT_ROWS = "COUNT_ROWS"
    COUNT_DISTINCT = "COUNT_DISTINCT"
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"


class ComparisonOperator(StrEnum):
    EQ = "EQ"
    NE = "NE"
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"


ScalarValue = str | int | float


class AggregateSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    operator: AggregateOperator
    table: str
    column: str | None = None
    evidence_id: str
    source_grain: str | None = Field(default=None, min_length=1, max_length=120)
    weight_column: str | None = None
    rounding_digits: int | None = Field(default=None, ge=0, le=15)

    @model_validator(mode="after")
    def validate_operand(self) -> Self:
        if self.operator is AggregateOperator.COUNT_ROWS and self.column is not None:
            raise ValueError("COUNT_ROWS must not name a column")
        if self.operator is not AggregateOperator.COUNT_ROWS and self.column is None:
            raise ValueError(f"{self.operator} requires a column")
        if self.weight_column is not None and self.operator is not AggregateOperator.AVG:
            raise ValueError("only AVG may declare a weight column")
        return self


class PredicateSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    table: str
    column: str
    operator: ComparisonOperator
    value: ScalarValue
    evidence_id: str


class FrequencyRankingSpec(BaseModel):
    """Typed proof for a bounded most-frequent-value query on one physical relation."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    table: str
    dimension_column: str
    evidence_id: str
    source_grain: str = Field(min_length=1, max_length=120)
    limit: int = Field(default=1, ge=1, le=100)
    descending_count: Literal[True] = True
    ascending_dimension_tie_break: Literal[True] = True


class SemanticBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    db_id: str
    catalog_hash: str
    status: BindingStatus
    aggregate: AggregateSpec | None = None
    frequency_ranking: FrequencyRankingSpec | None = None
    predicates: tuple[PredicateSpec, ...] = ()
    required_tables: tuple[str, ...] = ()
    required_columns: tuple[str, ...] = ()
    rule_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_proof(self) -> Self:
        proof_count = sum(item is not None for item in (self.aggregate, self.frequency_ranking))
        if self.status is BindingStatus.PROVEN and proof_count != 1:
            raise ValueError("a PROVEN binding requires exactly one typed proof")
        if self.frequency_ranking is not None and self.predicates:
            raise ValueError("frequency ranking does not support predicates")
        return self


class EntityRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    aliases: tuple[str, ...] = Field(min_length=1)
    table: str
    identity_column: str | None = None
    row_grain: str = Field(min_length=1, max_length=120)


class MetricRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    aliases: tuple[str, ...] = Field(min_length=1)
    operator: AggregateOperator
    table: str
    column: str | None = None
    allowed_operators: tuple[AggregateOperator, ...] = ()
    source_grain: str = Field(min_length=1, max_length=120)
    weight_column: str | None = None


class EnumValueRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    aliases: tuple[str, ...] = Field(min_length=1)
    value: ScalarValue


class FilterRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    table: str
    column: str
    values: dict[str, EnumValueRule]


class DerivedRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    aliases: tuple[str, ...] = Field(min_length=1)
    aggregate: AggregateSpec
    predicates: tuple[PredicateSpec, ...] = ()


class FrequencyRankingRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    aliases: tuple[str, ...] = Field(min_length=1)
    table: str
    dimension_column: str
    source_grain: str = Field(min_length=1, max_length=120)


class SemanticCatalog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: Literal[1]
    db_id: str
    entities: dict[str, EntityRule] = Field(default_factory=dict)
    metrics: dict[str, MetricRule] = Field(default_factory=dict)
    filters: dict[str, FilterRule] = Field(default_factory=dict)
    derived: dict[str, DerivedRule] = Field(default_factory=dict)
    frequency_rankings: dict[str, FrequencyRankingRule] = Field(default_factory=dict)
