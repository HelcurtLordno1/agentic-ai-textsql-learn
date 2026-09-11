"""Catalog-checked compilation for the provable scalar subset of grounded plans."""

from __future__ import annotations

from sqlglot import exp

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import DINSQLPlan, PlanningStrategy
from agentic_text2sql.contracts.semantics import (
    AggregateOperator,
    BindingStatus,
    ComparisonOperator,
    PredicateSpec,
    ScalarValue,
)
from agentic_text2sql.contracts.sql import CandidateRecord, SqlCandidate
from agentic_text2sql.layer3_generation.normalizer import CandidateNormalizer

GROUNDED_EASY_COMPILER_VERSION = "generator_v7_typed_semantic"
GROUNDED_EASY_COMPILER_MODEL = "deterministic-grounded-compiler"


class GroundedEasyCompiler:
    """Compile only scalar SQL whose full meaning is represented by a proven binding.

    Returning ``None`` deliberately hands control to model generation. Human-readable clause text
    is never parsed or trusted: the compiler consumes only typed aggregate and predicate contracts.
    """

    def __init__(self, normalizer: CandidateNormalizer) -> None:
        self.normalizer = normalizer
        self.prompt_version = GROUNDED_EASY_COMPILER_VERSION

    def compile(self, plan: DINSQLPlan, catalog: CatalogSnapshot) -> CandidateRecord | None:
        clauses = plan.clauses
        binding = plan.semantic_links.binding
        if (
            binding is None
            or binding.status is not BindingStatus.PROVEN
            or binding.db_id != catalog.db_id
            or binding.catalog_hash != catalog.catalog_hash
            or binding.aggregate is None
            or clauses.aggregate != binding.aggregate
            or tuple(clauses.predicates) != binding.predicates
            or plan.complexity.strategy is not PlanningStrategy.EASY
            or clauses.output_grain.casefold() != "one scalar row"
            or len(clauses.select) != 1
            or len(clauses.from_tables) != 1
            or clauses.joins
            or clauses.group_by
            or clauses.having
            or clauses.order_by
            or clauses.limit is not None
            or clauses.subqueries
            or clauses.set_operation is not None
        ):
            return None

        table_name = clauses.from_tables[0]
        owners = {
            binding.aggregate.table,
            *(predicate.table for predicate in binding.predicates),
        }
        if owners != {table_name} or set(binding.required_tables) != {table_name}:
            return None
        table = next((item for item in catalog.tables if item.name == table_name), None)
        if table is None:
            return None
        catalog_columns = {column.name for column in table.columns}
        if any(
            qualified.split(".", maxsplit=1)[0] != table_name
            or qualified.split(".", maxsplit=1)[-1] not in catalog_columns
            for qualified in binding.required_columns
        ):
            return None

        aggregate = binding.aggregate
        if aggregate.column is not None and aggregate.column not in catalog_columns:
            return None
        selection = _aggregate_expression(
            aggregate.operator,
            aggregate.column,
            aggregate.weight_column,
        )
        if selection is None:
            return None
        if aggregate.rounding_digits is not None:
            selection = exp.Round(
                this=selection,
                decimals=exp.Literal.number(aggregate.rounding_digits),
            )

        used_columns = [aggregate.column] if aggregate.column is not None else []
        if aggregate.weight_column is not None:
            if aggregate.weight_column not in catalog_columns:
                return None
            used_columns.append(aggregate.weight_column)
        predicates: list[exp.Expression] = []
        for predicate in binding.predicates:
            if predicate.column not in catalog_columns:
                return None
            used_columns.append(predicate.column)
            predicates.append(_predicate_expression(predicate))

        query = exp.select(selection).from_(table_name)
        if predicates:
            condition = predicates[0]
            for predicate_expression in predicates[1:]:
                condition = exp.and_(condition, predicate_expression)
            query = query.where(condition)

        candidate = SqlCandidate(
            sql=query.sql(dialect="sqlite"),
            used_tables=[table_name],
            used_columns=list(dict.fromkeys(used_columns)),
            assumptions=[],
            confidence=1.0,
        )
        return self.normalizer.normalize(
            candidate,
            model_name=GROUNDED_EASY_COMPILER_MODEL,
            prompt_version=self.prompt_version,
            catalog_hash=catalog.catalog_hash,
        )


def _aggregate_expression(
    operator: AggregateOperator,
    column: str | None,
    weight_column: str | None = None,
) -> exp.Expression | None:
    if operator is AggregateOperator.COUNT_ROWS:
        return exp.Count(this=exp.Star()) if column is None else None
    if column is None:
        return None
    operand = exp.column(column)
    if operator is AggregateOperator.AVG and weight_column is not None:
        weight = exp.column(weight_column)
        numerator = exp.Sum(this=exp.Mul(this=operand, expression=weight))
        denominator = exp.Nullif(
            this=exp.Sum(this=weight.copy()),
            expression=exp.Literal.number(0),
        )
        return exp.Div(this=numerator, expression=denominator)
    if operator is AggregateOperator.COUNT_DISTINCT:
        return exp.Count(this=exp.Distinct(expressions=[operand]))
    constructors: dict[AggregateOperator, type[exp.Expression]] = {
        AggregateOperator.SUM: exp.Sum,
        AggregateOperator.AVG: exp.Avg,
        AggregateOperator.MIN: exp.Min,
        AggregateOperator.MAX: exp.Max,
    }
    constructor = constructors.get(operator)
    return constructor(this=operand) if constructor is not None else None


def _literal(value: ScalarValue) -> exp.Expression:
    if isinstance(value, str):
        return exp.Literal.string(value)
    return exp.Literal.number(str(value))


def _predicate_expression(predicate: PredicateSpec) -> exp.Expression:
    left = exp.column(predicate.column)
    right = _literal(predicate.value)
    constructors: dict[ComparisonOperator, type[exp.Expression]] = {
        ComparisonOperator.EQ: exp.EQ,
        ComparisonOperator.NE: exp.NEQ,
        ComparisonOperator.GT: exp.GT,
        ComparisonOperator.GTE: exp.GTE,
        ComparisonOperator.LT: exp.LT,
        ComparisonOperator.LTE: exp.LTE,
    }
    return constructors[predicate.operator](this=left, expression=right)
