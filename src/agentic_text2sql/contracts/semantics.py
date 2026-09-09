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

    @model_validator(mode="after")
    def validate_operand(self) -> Self:
        if self.operator is AggregateOperator.COUNT_ROWS and self.column is not None:
            raise ValueError("COUNT_ROWS must not name a column")
        if self.operator is not AggregateOperator.COUNT_ROWS and self.column is None:
            raise ValueError(f"{self.operator} requires a column")
        return self


class PredicateSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    table: str
    column: str
    operator: ComparisonOperator
    value: ScalarValue
    evidence_id: str


class SemanticBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    db_id: str
    catalog_hash: str
    status: BindingStatus
    aggregate: AggregateSpec | None = None
    predicates: tuple[PredicateSpec, ...] = ()
    required_tables: tuple[str, ...] = ()
    required_columns: tuple[str, ...] = ()
    rule_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_proof(self) -> Self:
        if self.status is BindingStatus.PROVEN and self.aggregate is None:
            raise ValueError("a PROVEN binding requires an aggregate")
        return self


class EntityRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    aliases: tuple[str, ...] = Field(min_length=1)
    table: str
    identity_column: str | None = None


class MetricRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    aliases: tuple[str, ...] = Field(min_length=1)
    operator: AggregateOperator
    table: str
    column: str | None = None
    allowed_operators: tuple[AggregateOperator, ...] = ()


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


class SemanticCatalog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: Literal[1]
    db_id: str
    entities: dict[str, EntityRule] = Field(default_factory=dict)
    metrics: dict[str, MetricRule] = Field(default_factory=dict)
    filters: dict[str, FilterRule] = Field(default_factory=dict)
    derived: dict[str, DerivedRule] = Field(default_factory=dict)
