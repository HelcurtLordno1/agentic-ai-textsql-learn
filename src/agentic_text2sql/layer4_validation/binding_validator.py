"""Compare a SQL AST with a catalog-proven semantic binding."""

from __future__ import annotations

from sqlglot import exp

from agentic_text2sql.contracts.semantics import (
    AggregateOperator,
    ColumnComparisonSpec,
    ColumnRef,
    ComparisonOperator,
    PredicateSpec,
    SemanticBinding,
)
from agentic_text2sql.layer4_validation.parser import SQLParseError, parse_one


def _column_matches(expression: exp.Expression, column: str) -> bool:
    return any(
        item.name.casefold() == column.casefold() for item in expression.find_all(exp.Column)
    )


def _column_ref_matches(expression: exp.Expression, column: ColumnRef) -> bool:
    return any(
        item.name.casefold() == column.column.casefold()
        and item.table.casefold() == column.table.casefold()
        for item in expression.find_all(exp.Column)
    )


def _aggregate_matches(
    statement: exp.Expression, operator: AggregateOperator, column: str | None
) -> bool:
    if operator is AggregateOperator.COUNT_ROWS:
        return any(
            isinstance(item.this, exp.Star) and item.find(exp.Distinct) is None
            for item in statement.find_all(exp.Count)
        )
    if column is None:
        return False
    if operator is AggregateOperator.COUNT_DISTINCT:
        return any(
            item.find(exp.Distinct) is not None and _column_matches(item, column)
            for item in statement.find_all(exp.Count)
        )
    constructors: dict[AggregateOperator, type[exp.Expression]] = {
        AggregateOperator.SUM: exp.Sum,
        AggregateOperator.AVG: exp.Avg,
        AggregateOperator.MIN: exp.Min,
        AggregateOperator.MAX: exp.Max,
    }
    constructor = constructors.get(operator)
    return bool(
        constructor is not None
        and any(_column_matches(item, column) for item in statement.find_all(constructor))
    )


def _weighted_average_matches(
    statement: exp.Expression,
    value_column: str,
    weight_column: str,
) -> bool:
    """Recognize SUM(value * weight) / NULLIF(SUM(weight), 0)."""
    for division in statement.find_all(exp.Div):
        numerator = division.this
        denominator = division.expression
        if any(
            _column_matches(summation, value_column)
            and _column_matches(summation, weight_column)
            and summation.find(exp.Mul) is not None
            for summation in numerator.find_all(exp.Sum)
        ) and any(
            _column_matches(summation, weight_column) for summation in denominator.find_all(exp.Sum)
        ):
            return True
    return False


def _predicate_matches(statement: exp.Expression, predicate: PredicateSpec) -> bool:
    if predicate.operator is ComparisonOperator.IS_NULL:
        return any(
            _column_matches(item, predicate.column) and isinstance(item.expression, exp.Null)
            for item in statement.find_all(exp.Is)
            if not isinstance(item.parent, exp.Not)
        )
    if predicate.operator is ComparisonOperator.IS_NOT_NULL:
        return any(
            _column_matches(item, predicate.column) and isinstance(item.expression, exp.Null)
            for negation in statement.find_all(exp.Not)
            for item in negation.find_all(exp.Is)
        )
    constructors: dict[ComparisonOperator, type[exp.Expression]] = {
        ComparisonOperator.EQ: exp.EQ,
        ComparisonOperator.NE: exp.NEQ,
        ComparisonOperator.GT: exp.GT,
        ComparisonOperator.GTE: exp.GTE,
        ComparisonOperator.LT: exp.LT,
        ComparisonOperator.LTE: exp.LTE,
    }
    constructor = constructors.get(predicate.operator)
    if constructor is None:
        return False
    expected = str(predicate.value).casefold()
    return any(
        _column_matches(item, predicate.column)
        and any(literal.this.casefold() == expected for literal in item.find_all(exp.Literal))
        for item in statement.find_all(constructor)
    )


def _column_comparison_matches(statement: exp.Expression, comparison: ColumnComparisonSpec) -> bool:
    constructors: dict[ComparisonOperator, type[exp.Expression]] = {
        ComparisonOperator.EQ: exp.EQ,
        ComparisonOperator.NE: exp.NEQ,
        ComparisonOperator.GT: exp.GT,
        ComparisonOperator.GTE: exp.GTE,
        ComparisonOperator.LT: exp.LT,
        ComparisonOperator.LTE: exp.LTE,
    }
    constructor = constructors.get(comparison.operator)
    return bool(
        constructor is not None
        and any(
            _column_ref_matches(item.this, comparison.left)
            and _column_ref_matches(item.expression, comparison.right)
            for item in statement.find_all(constructor)
        )
    )


def validate_sql_against_binding(sql: str, binding: SemanticBinding) -> tuple[str, ...]:
    """Return named contradictions only; absence of a signal is not proof of correctness."""
    try:
        statement = parse_one(sql)
    except SQLParseError:
        return ("INCUMBENT_SQL_UNPARSEABLE",)
    tables = {table.name.casefold() for table in statement.find_all(exp.Table)}
    signals: list[str] = []
    ranking = binding.frequency_ranking
    aggregate = binding.aggregate
    owner = (
        ranking.table if ranking is not None else aggregate.table if aggregate is not None else None
    )
    if owner is None or owner.casefold() not in tables:
        signals.append("TYPED_OWNER_MISSING")
    expected_tables = {table.casefold() for table in binding.required_tables}
    if expected_tables - tables and owner is not None and owner.casefold() in tables:
        signals.append("TYPED_REQUIRED_OWNER_MISSING")
    if (
        owner is not None
        and owner.casefold() in tables
        and expected_tables
        and tables - expected_tables
    ):
        signals.append("TYPED_UNEXPECTED_OWNER")
    if ranking is not None:
        group = statement.find(exp.Group)
        if group is None or not any(
            _column_matches(expression, ranking.dimension_column)
            for expression in group.expressions
        ):
            signals.append("FREQUENCY_DIMENSION_GROUP_MISSING")
        if not _aggregate_matches(statement, AggregateOperator.COUNT_ROWS, None):
            signals.append("FREQUENCY_ROW_COUNT_MISSING")
        order = statement.find(exp.Order)
        ordered = list(order.expressions) if order is not None else []
        if not ordered or not bool(ordered[0].args.get("desc")):
            signals.append("FREQUENCY_COUNT_DESC_MISSING")
        if (
            len(ordered) < 2
            or bool(ordered[1].args.get("desc"))
            or not _column_matches(ordered[1], ranking.dimension_column)
        ):
            signals.append("FREQUENCY_DIMENSION_TIE_BREAK_MISSING")
        limit = statement.find(exp.Limit)
        literal = limit.expression if limit is not None else None
        actual_limit = int(literal.this) if isinstance(literal, exp.Literal) else None
        if actual_limit != ranking.limit:
            signals.append("TYPED_LIMIT_MISMATCH")
    elif aggregate is not None:
        weighted_average_matches = bool(
            aggregate.operator is AggregateOperator.AVG
            and aggregate.column is not None
            and aggregate.weight_column is not None
            and _weighted_average_matches(
                statement,
                aggregate.column,
                aggregate.weight_column,
            )
        )
        if not weighted_average_matches and not _aggregate_matches(
            statement, aggregate.operator, aggregate.column
        ):
            signals.append("TYPED_AGGREGATE_MISMATCH")
        if (
            aggregate.operator is AggregateOperator.AVG
            and aggregate.column is not None
            and aggregate.weight_column is not None
            and not weighted_average_matches
        ):
            signals.append("TYPED_WEIGHTED_AVERAGE_MISMATCH")
        if aggregate.rounding_digits is not None:
            rounds = list(statement.find_all(exp.Round))
            if not any(
                isinstance(item.args.get("decimals"), exp.Literal)
                and int(item.args["decimals"].this) == aggregate.rounding_digits
                for item in rounds
            ):
                signals.append("TYPED_ROUNDING_MISMATCH")
    for join in binding.joins:
        matched = any(
            (
                _column_ref_matches(item.this, join.left)
                and _column_ref_matches(item.expression, join.right)
            )
            or (
                _column_ref_matches(item.this, join.right)
                and _column_ref_matches(item.expression, join.left)
            )
            for item in statement.find_all(exp.EQ)
        )
        if not matched:
            signals.append(f"TYPED_JOIN_MISSING:{join.evidence_id}")
    for comparison in binding.column_comparisons:
        if not _column_comparison_matches(statement, comparison):
            signals.append(f"TYPED_COLUMN_COMPARISON_MISSING:{comparison.evidence_id}")
    grouping = binding.grouped_aggregate
    if grouping is not None:
        group = statement.find(exp.Group)
        if group is None or not any(
            _column_ref_matches(expression, grouping.dimension) for expression in group.expressions
        ):
            signals.append("TYPED_GROUP_DIMENSION_MISSING")
        order = statement.find(exp.Order)
        ordered = list(order.expressions) if order is not None else []
        if not ordered or not bool(ordered[0].args.get("desc")):
            signals.append("TYPED_AGGREGATE_ORDER_MISSING")
        if len(ordered) < 2 or bool(ordered[1].args.get("desc")):
            signals.append("TYPED_DIMENSION_TIE_BREAK_MISSING")
        limit = statement.find(exp.Limit)
        literal = limit.expression if limit is not None else None
        actual_limit = int(literal.this) if isinstance(literal, exp.Literal) else None
        if actual_limit != grouping.limit:
            signals.append("TYPED_LIMIT_MISMATCH")
    for predicate in binding.predicates:
        if not _predicate_matches(statement, predicate):
            signals.append(f"TYPED_PREDICATE_MISSING:{predicate.column}")
    return tuple(dict.fromkeys(signals))
