"""Catalog-checked compilation for the provable aggregate subset of grounded plans."""

from __future__ import annotations

from sqlglot import exp

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import DINSQLPlan, PlanningStrategy
from agentic_text2sql.contracts.semantics import (
    AggregateOperator,
    BindingStatus,
    ColumnComparisonSpec,
    ColumnRef,
    ComparisonOperator,
    GroupedAggregateSpec,
    PredicateSpec,
    ScalarValue,
)
from agentic_text2sql.contracts.sql import CandidateRecord, SqlCandidate
from agentic_text2sql.layer3_generation.normalizer import CandidateNormalizer

GROUNDED_EASY_COMPILER_VERSION = "generator_v9_relational_proof_compiler"
GROUNDED_EASY_COMPILER_MODEL = "deterministic-grounded-compiler"


class GroundedEasyCompiler:
    """Compile SQL only when its full aggregate meaning is represented by a proven binding.

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
        ):
            return None
        if binding.frequency_ranking is not None:
            return self._compile_frequency_ranking(plan, catalog)
        if binding.joins or binding.column_comparisons or binding.grouped_aggregate is not None:
            return self._compile_relational_aggregate(plan, catalog)
        if (
            binding.aggregate is None
            or clauses.aggregate != binding.aggregate
            or clauses.frequency_ranking is not None
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

    def _compile_relational_aggregate(
        self, plan: DINSQLPlan, catalog: CatalogSnapshot
    ) -> CandidateRecord | None:
        clauses = plan.clauses
        binding = plan.semantic_links.binding
        if binding is None or binding.aggregate is None:
            return None
        if (
            clauses.aggregate != binding.aggregate
            or tuple(clauses.predicates) != binding.predicates
            or tuple(clauses.semantic_joins) != binding.joins
            or tuple(clauses.column_comparisons) != binding.column_comparisons
            or clauses.grouped_aggregate != binding.grouped_aggregate
            or plan.complexity.strategy is not PlanningStrategy.NON_NESTED
            or set(clauses.from_tables) != set(binding.required_tables)
            or clauses.subqueries
            or clauses.set_operation is not None
        ):
            return None
        catalog_columns = {
            f"{table.name}.{column.name}" for table in catalog.tables for column in table.columns
        }
        if set(binding.required_columns) - catalog_columns:
            return None

        aggregate = binding.aggregate
        selection = _aggregate_expression(
            aggregate.operator,
            aggregate.column,
            aggregate.weight_column,
            table=aggregate.table,
        )
        if selection is None:
            return None
        if aggregate.rounding_digits is not None:
            selection = exp.Round(
                this=selection,
                decimals=exp.Literal.number(aggregate.rounding_digits),
            )

        grouping = binding.grouped_aggregate
        dimension = _grouped_dimension_expression(grouping) if grouping is not None else None
        selections = (
            [
                dimension.copy().as_(grouping.dimension_alias),
                selection.as_(grouping.aggregate_alias),
            ]
            if grouping is not None and dimension is not None
            else [selection]
        )
        query = exp.select(*selections).from_(aggregate.table)
        joined = {aggregate.table}
        for join in binding.joins:
            if join.left.table not in joined or join.right.table in joined:
                return None
            join_condition = exp.EQ(
                this=_column_expression(join.left),
                expression=_column_expression(join.right),
            )
            query = query.join(join.right.table, on=join_condition, join_type=join.kind.value)
            joined.add(join.right.table)
        if joined != set(binding.required_tables):
            return None

        predicates = [
            *(_predicate_expression(predicate, qualify=True) for predicate in binding.predicates),
            *(_column_comparison_expression(item) for item in binding.column_comparisons),
        ]
        if predicates:
            predicate_condition = predicates[0]
            for predicate_expression in predicates[1:]:
                predicate_condition = exp.and_(predicate_condition, predicate_expression)
            query = query.where(predicate_condition)
        if grouping is not None and dimension is not None:
            query = (
                query.group_by(dimension.copy())
                .order_by(
                    exp.column(grouping.aggregate_alias).desc(),
                    exp.column(grouping.dimension_alias).asc(),
                )
                .limit(grouping.limit)
            )

        candidate = SqlCandidate(
            sql=query.sql(dialect="sqlite"),
            used_tables=list(binding.required_tables),
            used_columns=[value.split(".", maxsplit=1)[1] for value in binding.required_columns],
            assumptions=[],
            confidence=1.0,
        )
        return self.normalizer.normalize(
            candidate,
            model_name=GROUNDED_EASY_COMPILER_MODEL,
            prompt_version=self.prompt_version,
            catalog_hash=catalog.catalog_hash,
        )

    def _compile_frequency_ranking(
        self, plan: DINSQLPlan, catalog: CatalogSnapshot
    ) -> CandidateRecord | None:
        clauses = plan.clauses
        binding = plan.semantic_links.binding
        if binding is None or binding.frequency_ranking is None:
            return None
        ranking = binding.frequency_ranking
        if (
            clauses.frequency_ranking != ranking
            or clauses.aggregate is not None
            or clauses.predicates
            or plan.complexity.strategy is not PlanningStrategy.EASY
            or len(clauses.select) != 2
            or clauses.from_tables != [ranking.table]
            or clauses.joins
            or clauses.where
            or len(clauses.group_by) != 1
            or clauses.having
            or len(clauses.order_by) != 2
            or clauses.limit != ranking.limit
            or clauses.subqueries
            or clauses.set_operation is not None
            or set(binding.required_tables) != {ranking.table}
            or set(binding.required_columns) != {f"{ranking.table}.{ranking.dimension_column}"}
        ):
            return None
        table = next((item for item in catalog.tables if item.name == ranking.table), None)
        if table is None or ranking.dimension_column not in {
            column.name for column in table.columns
        }:
            return None

        dimension = exp.column(ranking.dimension_column)
        count_alias = "frequency_count"
        query = (
            exp.select(dimension.copy(), exp.Count(this=exp.Star()).as_(count_alias))
            .from_(ranking.table)
            .group_by(dimension.copy())
            .order_by(exp.column(count_alias).desc(), dimension.copy().asc())
            .limit(ranking.limit)
        )
        candidate = SqlCandidate(
            sql=query.sql(dialect="sqlite"),
            used_tables=[ranking.table],
            used_columns=[ranking.dimension_column],
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
    *,
    table: str | None = None,
) -> exp.Expression | None:
    if operator is AggregateOperator.COUNT_ROWS:
        return exp.Count(this=exp.Star()) if column is None else None
    if column is None:
        return None
    operand = exp.column(column, table=table)
    if operator is AggregateOperator.AVG and weight_column is not None:
        weight = exp.column(weight_column, table=table)
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
    if value is None:
        return exp.Null()
    if isinstance(value, str):
        return exp.Literal.string(value)
    return exp.Literal.number(str(value))


def _predicate_expression(predicate: PredicateSpec, *, qualify: bool = False) -> exp.Expression:
    left = exp.column(predicate.column, table=predicate.table if qualify else None)
    if predicate.operator is ComparisonOperator.IS_NULL:
        return exp.Is(this=left, expression=exp.Null())
    if predicate.operator is ComparisonOperator.IS_NOT_NULL:
        return exp.Not(this=exp.Is(this=left, expression=exp.Null()))
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


def _column_expression(column: ColumnRef) -> exp.Column:
    return exp.column(column.column, table=column.table)


def _column_comparison_expression(comparison: ColumnComparisonSpec) -> exp.Expression:
    constructors: dict[ComparisonOperator, type[exp.Expression]] = {
        ComparisonOperator.EQ: exp.EQ,
        ComparisonOperator.NE: exp.NEQ,
        ComparisonOperator.GT: exp.GT,
        ComparisonOperator.GTE: exp.GTE,
        ComparisonOperator.LT: exp.LT,
        ComparisonOperator.LTE: exp.LTE,
    }
    return constructors[comparison.operator](
        this=_column_expression(comparison.left),
        expression=_column_expression(comparison.right),
    )


def _grouped_dimension_expression(grouping: GroupedAggregateSpec) -> exp.Expression:
    expressions: list[exp.Expression] = [
        _column_expression(grouping.dimension),
        *(_column_expression(column) for column in grouping.fallback_columns),
    ]
    if grouping.null_fallback is not None:
        expressions.append(_literal(grouping.null_fallback))
    if len(expressions) == 1:
        return expressions[0]
    return exp.Coalesce(this=expressions[0], expressions=expressions[1:])
