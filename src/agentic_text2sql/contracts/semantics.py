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
    IS_NULL = "IS_NULL"
    IS_NOT_NULL = "IS_NOT_NULL"


ScalarValue = str | int | float | None


class JoinKind(StrEnum):
    INNER = "INNER"
    LEFT = "LEFT"


class JoinCardinality(StrEnum):
    ONE_TO_ONE = "ONE_TO_ONE"
    MANY_TO_ONE = "MANY_TO_ONE"


class ColumnRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    table: str
    column: str


class JoinSpec(BaseModel):
    """A catalog-declared join that cannot fan out the current left-hand grain."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    left: ColumnRef
    right: ColumnRef
    kind: JoinKind = JoinKind.INNER
    cardinality: JoinCardinality
    evidence_id: str


class ColumnComparisonSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    left: ColumnRef
    operator: ComparisonOperator
    right: ColumnRef
    evidence_id: str

    @model_validator(mode="after")
    def validate_ordered_operator(self) -> Self:
        if self.operator in {ComparisonOperator.IS_NULL, ComparisonOperator.IS_NOT_NULL}:
            raise ValueError("column comparisons cannot use null operators")
        return self


class GroupedAggregateSpec(BaseModel):
    """Bounded grouped ranking over one dimension and one aggregate."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    dimension: ColumnRef
    fallback_columns: tuple[ColumnRef, ...] = ()
    null_fallback: ScalarValue = None
    dimension_alias: str = Field(default="dimension_value", pattern=r"^[a-z][a-z0-9_]{0,39}$")
    aggregate_alias: str = Field(default="aggregate_value", pattern=r"^[a-z][a-z0-9_]{0,39}$")
    aggregate_descending: Literal[True] = True
    dimension_ascending_tie_break: Literal[True] = True
    limit: int = Field(ge=1, le=100)


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

    @model_validator(mode="after")
    def validate_null_operator(self) -> Self:
        null_operator = self.operator in {
            ComparisonOperator.IS_NULL,
            ComparisonOperator.IS_NOT_NULL,
        }
        if null_operator != (self.value is None):
            raise ValueError("null predicates require a null operator and null value")
        return self


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
    joins: tuple[JoinSpec, ...] = ()
    column_comparisons: tuple[ColumnComparisonSpec, ...] = ()
    grouped_aggregate: GroupedAggregateSpec | None = None
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
        if self.frequency_ranking is not None and (
            self.joins or self.column_comparisons or self.grouped_aggregate is not None
        ):
            raise ValueError("frequency ranking does not support relational proof fields")
        if self.grouped_aggregate is not None and self.aggregate is None:
            raise ValueError("grouped aggregate metadata requires an aggregate proof")
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
    alternate_sources: tuple["MetricSourceRule", ...] = ()


class MetricSourceRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    table: str
    column: str
    source_grain: str = Field(min_length=1, max_length=120)
    weight_column: str | None = None


class DimensionRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    aliases: tuple[str, ...] = Field(min_length=1)
    table: str
    column: str
    fallback_columns: tuple[str, ...] = ()
    null_fallback: ScalarValue = None
    source_grain: str = Field(min_length=1, max_length=120)


class JoinRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    cardinality: JoinCardinality


class EnumValueRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    aliases: tuple[str, ...] = Field(min_length=1)
    value: ScalarValue


class FilterRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    table: str
    column: str
    values: dict[str, EnumValueRule]


class PredicateRule(BaseModel):
    """Catalog-backed scalar predicate parsed from generic operator/value language."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    aliases: tuple[str, ...] = Field(min_length=1)
    table: str
    column: str
    kind: Literal["null", "numeric_equality"]
    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if self.kind == "null" and (self.minimum is not None or self.maximum is not None):
            raise ValueError("null predicate rules cannot declare numeric bounds")
        if self.kind == "numeric_equality":
            if self.minimum is None or self.maximum is None:
                raise ValueError("numeric predicate rules require minimum and maximum")
            if self.minimum > self.maximum:
                raise ValueError("numeric predicate minimum exceeds maximum")
        return self


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
    dimensions: dict[str, DimensionRule] = Field(default_factory=dict)
    joins: dict[str, JoinRule] = Field(default_factory=dict)
    filters: dict[str, FilterRule] = Field(default_factory=dict)
    predicate_rules: dict[str, PredicateRule] = Field(default_factory=dict)
    derived: dict[str, DerivedRule] = Field(default_factory=dict)
    frequency_rankings: dict[str, FrequencyRankingRule] = Field(default_factory=dict)
