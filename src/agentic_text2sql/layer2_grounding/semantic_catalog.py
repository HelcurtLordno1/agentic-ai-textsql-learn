"""Schema-validated semantic catalog and conservative scalar intent resolver."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import yaml

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import DecomposedQuestion
from agentic_text2sql.contracts.semantics import (
    AggregateOperator,
    AggregateSpec,
    BindingStatus,
    ComparisonOperator,
    PredicateSpec,
    SemanticBinding,
    SemanticCatalog,
)

_COUNT_MARKERS = (
    "how many",
    "number of",
    "count of",
    "count all",
    "bao nhiêu",
    "số lượng",
    "đếm",
)
_DISTINCT_MARKERS = ("distinct", "unique", "duy nhất", "khác nhau")
_METRIC_OPERATOR_MARKERS = {
    AggregateOperator.SUM: ("total", "sum", "tổng"),
    AggregateOperator.AVG: ("average", "avg", "trung bình"),
    AggregateOperator.MIN: ("minimum", "min", "nhỏ nhất", "thấp nhất"),
    AggregateOperator.MAX: ("maximum", "max", "lớn nhất", "cao nhất"),
}
_UNSUPPORTED_SCALAR_MARKERS = (
    " per ",
    " by ",
    " theo ",
    " mỗi ",
    " each ",
    " top ",
    "highest",
    "lowest",
)
_QUALIFIER_MARKERS = (
    " where ",
    " with ",
    " whose ",
    " that ",
    " before ",
    " after ",
    " between ",
    " greater than ",
    " less than ",
    " trước ",
    " sau ",
    " từ ",
)


class _HasAliases(Protocol):
    aliases: tuple[str, ...]


def _normalize(text: str) -> str:
    return " ".join(text.casefold().strip().split())


def _contains_alias(question: str, alias: str) -> bool:
    normalized_alias = _normalize(alias)
    if "_" in normalized_alias:
        return normalized_alias in question
    return re.search(rf"(?<!\w){re.escape(normalized_alias)}(?!\w)", question) is not None


def _qualified(table: str, column: str) -> str:
    return f"{table}.{column}"


def _identifier_sets(catalog: CatalogSnapshot) -> tuple[set[str], set[str]]:
    tables = {table.name for table in catalog.tables}
    columns = {
        _qualified(table.name, column.name) for table in catalog.tables for column in table.columns
    }
    return tables, columns


def _validate_aliases[T: _HasAliases](kind: str, rules: dict[str, T]) -> None:
    owners: dict[str, str] = {}
    for name, rule in rules.items():
        for alias in rule.aliases:
            normalized = _normalize(alias)
            if not normalized:
                raise ValueError(f"semantic {kind} {name} contains an empty alias")
            prior = owners.get(normalized)
            if prior is not None and prior != name:
                raise ValueError(
                    f"semantic {kind} alias {normalized!r} belongs to both {prior} and {name}"
                )
            owners[normalized] = name


def _validate_aggregate(
    aggregate: AggregateSpec, tables: set[str], columns: set[str], *, rule_id: str
) -> None:
    if aggregate.table not in tables:
        raise ValueError(f"semantic rule {rule_id} references unknown table {aggregate.table}")
    if aggregate.operator is AggregateOperator.COUNT_ROWS:
        if aggregate.column is not None:
            raise ValueError(f"semantic rule {rule_id} COUNT_ROWS must not name a column")
    elif aggregate.column is None or _qualified(aggregate.table, aggregate.column) not in columns:
        raise ValueError(f"semantic rule {rule_id} references an unknown aggregate column")


def validate_semantic_catalog(semantic_catalog: SemanticCatalog, catalog: CatalogSnapshot) -> None:
    """Fail startup when semantic rules do not agree with the introspected database."""
    if semantic_catalog.db_id != catalog.db_id:
        raise ValueError("semantic catalog db_id does not match the schema catalog")
    tables, columns = _identifier_sets(catalog)
    _validate_aliases("entity", semantic_catalog.entities)
    _validate_aliases("metric", semantic_catalog.metrics)
    _validate_aliases("derived", semantic_catalog.derived)
    for name, entity_rule in semantic_catalog.entities.items():
        if entity_rule.table not in tables:
            raise ValueError(f"semantic entity {name} references unknown table {entity_rule.table}")
        if (
            entity_rule.identity_column is not None
            and _qualified(entity_rule.table, entity_rule.identity_column) not in columns
        ):
            raise ValueError(f"semantic entity {name} references unknown identity column")
    for name, metric_rule in semantic_catalog.metrics.items():
        allowed_operators = metric_rule.allowed_operators or (metric_rule.operator,)
        if len(allowed_operators) != len(set(allowed_operators)):
            raise ValueError(f"semantic metric {name} repeats an allowed operator")
        if metric_rule.operator not in allowed_operators:
            raise ValueError(f"semantic metric {name} excludes its default operator")
        for operator in allowed_operators:
            _validate_aggregate(
                AggregateSpec(
                    operator=operator,
                    table=metric_rule.table,
                    column=metric_rule.column,
                    evidence_id=f"semantic.metric.{name}",
                ),
                tables,
                columns,
                rule_id=f"metric.{name}",
            )
    for name, filter_rule in semantic_catalog.filters.items():
        if _qualified(filter_rule.table, filter_rule.column) not in columns:
            raise ValueError(f"semantic filter {name} references unknown column")
        _validate_aliases(f"filter {name}", filter_rule.values)
    for name, derived_rule in semantic_catalog.derived.items():
        _validate_aggregate(derived_rule.aggregate, tables, columns, rule_id=f"derived.{name}")
        for predicate in derived_rule.predicates:
            if _qualified(predicate.table, predicate.column) not in columns:
                raise ValueError(
                    f"semantic derived rule {name} references unknown predicate column"
                )
        owners = {
            derived_rule.aggregate.table,
            *(predicate.table for predicate in derived_rule.predicates),
        }
        if len(owners) != 1:
            raise ValueError(f"semantic derived rule {name} is not a single-owner scalar rule")


def load_semantic_catalog(path: Path, catalog: CatalogSnapshot) -> SemanticCatalog:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    semantic_catalog = SemanticCatalog.model_validate(payload)
    validate_semantic_catalog(semantic_catalog, catalog)
    return semantic_catalog


def _matched_rules[T: _HasAliases](question: str, rules: dict[str, T]) -> list[tuple[str, T]]:
    return [
        (name, rule)
        for name, rule in rules.items()
        if any(_contains_alias(question, alias) for alias in rule.aliases)
    ]


def _unresolved_shape_marker(
    question: str,
    matched_rules: Sequence[tuple[str, _HasAliases]],
) -> bool:
    for marker in _UNSUPPORTED_SCALAR_MARKERS:
        if marker not in question:
            continue
        if not any(
            marker.strip() in _normalize(alias) and _contains_alias(question, alias)
            for _, rule in matched_rules
            for alias in rule.aliases
        ):
            return True
    return False


def _requested_metric_operators(question: str) -> tuple[AggregateOperator, ...]:
    return tuple(
        operator
        for operator, markers in _METRIC_OPERATOR_MARKERS.items()
        if any(_contains_alias(question, marker) for marker in markers)
    )


def _hints_covered_by_rules(
    question: str,
    hints: list[str],
    matched_rules: Sequence[tuple[str, _HasAliases]],
) -> bool:
    return bool(hints) and all(
        any(
            _normalize(hint) in _normalize(alias) and _contains_alias(question, alias)
            for _, rule in matched_rules
            for alias in rule.aliases
        )
        for hint in hints
    )


def resolve_semantic_binding(
    question: str,
    decomposition: DecomposedQuestion,
    catalog: CatalogSnapshot,
    semantic_catalog: SemanticCatalog | None,
) -> SemanticBinding:
    """Resolve only scalar semantics that are completely proven by catalog-backed rules."""
    if semantic_catalog is None:
        return SemanticBinding(
            db_id=catalog.db_id,
            catalog_hash=catalog.catalog_hash,
            status=BindingStatus.INCOMPLETE,
            reasons=("NO_SEMANTIC_CATALOG",),
        )
    normalized = f" {_normalize(question)} "
    derived = _matched_rules(normalized, semantic_catalog.derived)
    metrics = _matched_rules(normalized, semantic_catalog.metrics)
    entities = _matched_rules(normalized, semantic_catalog.entities)
    asks_count = any(marker in normalized for marker in _COUNT_MARKERS)
    derived_operator_is_explicit = bool(
        len(derived) == 1
        and (derived[0][1].aggregate.operator is not AggregateOperator.COUNT_ROWS or asks_count)
    )
    count_entity_names = {name.removesuffix("s") for name, _ in entities}
    count_dimensions_are_entities = bool(decomposition.dimension_hints) and all(
        dimension.removesuffix("s") in count_entity_names
        for dimension in decomposition.dimension_hints
    )
    dimensions_are_rule_semantics = _hints_covered_by_rules(
        normalized,
        decomposition.dimension_hints,
        [*derived, *metrics],
    )
    scalar_shape = not (
        (
            decomposition.dimension_hints
            and not (asks_count and count_dimensions_are_entities)
            and not dimensions_are_rule_semantics
            and not derived_operator_is_explicit
        )
        or decomposition.sort_hints
        or decomposition.limit_hint is not None
        or decomposition.time_hints
        or decomposition.set_operation_hint is not None
        or _unresolved_shape_marker(normalized, [*derived, *metrics])
    )
    if len(derived) > 1:
        return SemanticBinding(
            db_id=catalog.db_id,
            catalog_hash=catalog.catalog_hash,
            status=BindingStatus.AMBIGUOUS,
            reasons=("MULTIPLE_DERIVED_RULES",),
        )
    if len(derived) == 1 and scalar_shape and derived_operator_is_explicit:
        name, derived_rule = derived[0]
        required_columns = [
            *(
                [_qualified(derived_rule.aggregate.table, derived_rule.aggregate.column)]
                if derived_rule.aggregate.column is not None
                else []
            ),
            *(_qualified(item.table, item.column) for item in derived_rule.predicates),
        ]
        return SemanticBinding(
            db_id=catalog.db_id,
            catalog_hash=catalog.catalog_hash,
            status=BindingStatus.PROVEN,
            aggregate=derived_rule.aggregate,
            predicates=derived_rule.predicates,
            required_tables=tuple(
                dict.fromkeys(
                    [
                        derived_rule.aggregate.table,
                        *(item.table for item in derived_rule.predicates),
                    ]
                )
            ),
            required_columns=tuple(dict.fromkeys(required_columns)),
            rule_ids=(f"derived.{name}",),
        )

    if len(metrics) > 1 or (not metrics and len(entities) > 1):
        return SemanticBinding(
            db_id=catalog.db_id,
            catalog_hash=catalog.catalog_hash,
            status=BindingStatus.AMBIGUOUS,
            reasons=("MULTIPLE_METRIC_OR_ENTITY_RULES",),
        )

    aggregate: AggregateSpec | None = None
    rule_ids: list[str] = []
    operator_reason: str | None = None
    if len(metrics) == 1:
        name, metric_rule = metrics[0]
        requested_operators = _requested_metric_operators(normalized)
        allowed_operators = metric_rule.allowed_operators or (metric_rule.operator,)
        selected_operator = (
            requested_operators[0] if len(requested_operators) == 1 else metric_rule.operator
        )
        if len(requested_operators) > 1:
            operator_reason = "MULTIPLE_AGGREGATE_OPERATORS"
        elif selected_operator not in allowed_operators:
            operator_reason = "AGGREGATE_OPERATOR_NOT_ALLOWED"
        elif asks_count:
            operator_reason = "COUNT_METRIC_CONFLICT"
        aggregate = AggregateSpec(
            operator=selected_operator,
            table=metric_rule.table,
            column=metric_rule.column,
            evidence_id=f"semantic.metric.{name}",
        )
        rule_ids.append(f"metric.{name}")
    elif len(entities) == 1 and any(marker in normalized for marker in _COUNT_MARKERS):
        name, entity_rule = entities[0]
        explicit_columns = [
            column.name
            for table in catalog.tables
            if table.name == entity_rule.table
            for column in table.columns
            if _contains_alias(normalized, column.name)
        ]
        distinct = any(marker in normalized for marker in _DISTINCT_MARKERS)
        identity = (
            explicit_columns[0] if len(explicit_columns) == 1 else entity_rule.identity_column
        )
        if distinct and identity is None:
            return SemanticBinding(
                db_id=catalog.db_id,
                catalog_hash=catalog.catalog_hash,
                status=BindingStatus.INCOMPLETE,
                reasons=("DISTINCT_IDENTITY_UNRESOLVED",),
            )
        aggregate = AggregateSpec(
            operator=(
                AggregateOperator.COUNT_DISTINCT if distinct else AggregateOperator.COUNT_ROWS
            ),
            table=entity_rule.table,
            column=identity if distinct else None,
            evidence_id=f"semantic.entity.{name}",
        )
        rule_ids.append(f"entity.{name}")

    predicates: list[PredicateSpec] = []
    for name, filter_rule in semantic_catalog.filters.items():
        matches = [
            value_rule
            for value_rule in filter_rule.values.values()
            if any(_contains_alias(normalized, alias) for alias in value_rule.aliases)
        ]
        if len(matches) > 1:
            return SemanticBinding(
                db_id=catalog.db_id,
                catalog_hash=catalog.catalog_hash,
                status=BindingStatus.AMBIGUOUS,
                reasons=(f"MULTIPLE_FILTER_VALUES:{name}",),
            )
        if matches:
            predicates.append(
                PredicateSpec(
                    table=filter_rule.table,
                    column=filter_rule.column,
                    operator=ComparisonOperator.EQ,
                    value=matches[0].value,
                    evidence_id=f"semantic.filter.{name}",
                )
            )
            rule_ids.append(f"filter.{name}")

    reasons: list[str] = []
    if not scalar_shape:
        reasons.append("NON_SCALAR_SHAPE")
    if aggregate is None:
        reasons.append("AGGREGATE_UNRESOLVED")
    if decomposition.filter_hints and not predicates:
        reasons.append("FILTER_UNRESOLVED")
    if operator_reason is not None:
        reasons.append(operator_reason)
    if any(marker in normalized for marker in _QUALIFIER_MARKERS) and not predicates:
        reasons.append("QUALIFIER_UNRESOLVED")
    owners = {
        *(item.table for item in predicates),
        *((aggregate.table,) if aggregate is not None else ()),
    }
    if len(owners) > 1:
        reasons.append("MULTI_TABLE_BINDING")
    status = BindingStatus.PROVEN if not reasons else BindingStatus.INCOMPLETE
    required_columns = [
        *(
            [_qualified(aggregate.table, aggregate.column)]
            if aggregate is not None and aggregate.column is not None
            else []
        ),
        *(_qualified(item.table, item.column) for item in predicates),
    ]
    return SemanticBinding(
        db_id=catalog.db_id,
        catalog_hash=catalog.catalog_hash,
        status=status,
        aggregate=aggregate,
        predicates=tuple(predicates),
        required_tables=tuple(sorted(owners)),
        required_columns=tuple(dict.fromkeys(required_columns)),
        rule_ids=tuple(dict.fromkeys(rule_ids)),
        reasons=tuple(reasons),
    )
