"""Schema-validated semantic catalog and conservative scalar intent resolver."""

from __future__ import annotations

import re
from collections import deque
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
    ColumnComparisonSpec,
    ColumnRef,
    ComparisonOperator,
    EntityRule,
    FrequencyRankingSpec,
    GroupedAggregateSpec,
    JoinCardinality,
    JoinKind,
    JoinRule,
    JoinSpec,
    MetricRule,
    MetricSourceRule,
    PredicateRule,
    PredicateSpec,
    SemanticBinding,
    SemanticCatalog,
)

_COUNT_MARKERS = (
    "how many",
    "number of",
    "count of",
    "count all",
    "count ",
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
_ROUNDING_PATTERNS = (
    re.compile(r"\bround(?:ed)?\s+to\s+(\d+)\s+decimal"),
    re.compile(r"\blàm tròn\s+(\d+)\s+chữ số"),
)
_NULL_MARKERS = (
    re.compile(r"\b(?:missing|lacking|is\s+null|are\s+null)\b"),
    re.compile(r"\b(?:thiếu|bị\s+thiếu|là\s+null)\b"),
)
_NOT_NULL_MARKERS = (
    re.compile(r"\b(?:non[ -]?null|not\s+null|is\s+not\s+null|are\s+not\s+null)\b"),
    re.compile(r"\b(?:không\s+null|không\s+bị\s+thiếu)\b"),
)
_ORDERED_COMPARISON_PATTERNS = (
    re.compile(r"\b(?:more|greater|less|fewer)\s+than\b"),
    re.compile(r"\b(?:over|under|above|below|positive)\b"),
    re.compile(r"\b(?:hơn|trên|dưới|dương)\b"),
)
_EXACT_COMPARISON_PATTERNS = (
    re.compile(r"\b(?:exactly|equal(?:s|\s+to)?)\b"),
    re.compile(r"\b(?:bằng(?:\s+đúng)?)\b"),
)
_COLUMN_COMPARISON_PATTERNS = (
    re.compile(r"\b(?:actual)\b.{0,80}\b(?:estimated)\b"),
    re.compile(r"\b(?:versus|vs\.?)\b"),
)
_METRIC_COMPARISON_OPERATORS = (
    (re.compile(r"\b(?:greater|more|higher)\s+than\b|\blarger\s+than\b"), ComparisonOperator.GT),
    (re.compile(r"\b(?:less|lower|smaller)\s+than\b"), ComparisonOperator.LT),
    (re.compile(r"\b(?:lớn|cao|nhiều)\s+hơn\b"), ComparisonOperator.GT),
    (re.compile(r"\b(?:nhỏ|thấp|ít)\s+hơn\b"), ComparisonOperator.LT),
)
_INTERSECTION_MARKERS = (" both ", " cả hai ", " đồng thời ", " cùng có ")
_ANTI_JOIN_PATTERNS = (
    re.compile(r"\b(?:do|does|did)\s+not\s+have\b"),
    re.compile(r"\bwithout\b"),
    re.compile(r"\bkhông\s+có\b"),
)
_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "không": 0,
    "một": 1,
    "hai": 2,
    "ba": 3,
    "bốn": 4,
    "năm": 5,
    "sáu": 6,
    "bảy": 7,
    "tám": 8,
    "chín": 9,
    "mười": 10,
}
_NUMERIC_EQUALITY_PATTERNS = (
    re.compile(
        r"\b(?:of\s+)?(?:exactly|equal(?:s|\s+to)?|is)\s+"
        r"(zero|one|two|three|four|five|six|seven|eight|nine|ten|-?\d+(?:\.\d+)?)\b"
    ),
    re.compile(
        r"\b(?:bằng(?:\s+đúng)?|là)\s+"
        r"(không|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|-?\d+(?:\.\d+)?)\b"
    ),
)


class _HasAliases(Protocol):
    aliases: tuple[str, ...]


def _normalize(text: str) -> str:
    return " ".join(text.casefold().strip().split())


def _contains_alias(question: str, alias: str) -> bool:
    normalized_alias = _normalize(alias)
    if "_" in normalized_alias:
        if normalized_alias in question:
            return True
        # Compositional aliases containing an explicit schema identifier may tolerate short
        # natural-language modifiers between their ordered terms.  This keeps matching anchored
        # by the exact identifier while handling phrases such as "maximum ... for a
        # customer_unique_id" without fuzzy embedding guesses.
        terms = normalized_alias.split()
        if len(terms) < 2:
            return False
        cursor = 0
        start: int | None = None
        end = 0
        for term in terms:
            match = re.search(rf"(?<!\w){re.escape(term)}(?!\w)", question[cursor:])
            if match is None:
                return False
            absolute_start = cursor + match.start()
            end = cursor + match.end()
            if start is None:
                start = absolute_start
            cursor = end
        return start is not None and end - start <= 160
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
    if (
        aggregate.weight_column is not None
        and _qualified(aggregate.table, aggregate.weight_column) not in columns
    ):
        raise ValueError(f"semantic rule {rule_id} references an unknown weight column")


def validate_semantic_catalog(semantic_catalog: SemanticCatalog, catalog: CatalogSnapshot) -> None:
    """Fail startup when semantic rules do not agree with the introspected database."""
    if semantic_catalog.db_id != catalog.db_id:
        raise ValueError("semantic catalog db_id does not match the schema catalog")
    tables, columns = _identifier_sets(catalog)
    _validate_aliases("entity", semantic_catalog.entities)
    _validate_aliases("metric", semantic_catalog.metrics)
    _validate_aliases("dimension", semantic_catalog.dimensions)
    _validate_aliases("derived", semantic_catalog.derived)
    _validate_aliases("frequency ranking", semantic_catalog.frequency_rankings)
    _validate_aliases("predicate", semantic_catalog.predicate_rules)
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
                    source_grain=metric_rule.source_grain,
                    weight_column=(
                        metric_rule.weight_column if operator is AggregateOperator.AVG else None
                    ),
                ),
                tables,
                columns,
                rule_id=f"metric.{name}",
            )
        for source in metric_rule.alternate_sources:
            if _qualified(source.table, source.column) not in columns:
                raise ValueError(f"semantic metric {name} alternate source is unknown")
            if (
                source.weight_column is not None
                and _qualified(source.table, source.weight_column) not in columns
            ):
                raise ValueError(f"semantic metric {name} alternate weight is unknown")
    for name, dimension_rule in semantic_catalog.dimensions.items():
        dimension_columns = (
            dimension_rule.column,
            *dimension_rule.fallback_columns,
        )
        if any(
            _qualified(dimension_rule.table, column) not in columns for column in dimension_columns
        ):
            raise ValueError(f"semantic dimension {name} references an unknown column")
    for name, join_rule in semantic_catalog.joins.items():
        if (
            _qualified(join_rule.left_table, join_rule.left_column) not in columns
            or _qualified(join_rule.right_table, join_rule.right_column) not in columns
        ):
            raise ValueError(f"semantic join {name} references an unknown endpoint")
    for name, filter_rule in semantic_catalog.filters.items():
        if _qualified(filter_rule.table, filter_rule.column) not in columns:
            raise ValueError(f"semantic filter {name} references unknown column")
        _validate_aliases(f"filter {name}", filter_rule.values)
    for name, predicate_rule in semantic_catalog.predicate_rules.items():
        if _qualified(predicate_rule.table, predicate_rule.column) not in columns:
            raise ValueError(f"semantic predicate {name} references unknown column")
    for name, derived_rule in semantic_catalog.derived.items():
        _validate_aggregate(derived_rule.aggregate, tables, columns, rule_id=f"derived.{name}")
        if derived_rule.aggregate.source_grain is None:
            raise ValueError(f"semantic derived rule {name} does not declare its source grain")
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
    for name, ranking_rule in semantic_catalog.frequency_rankings.items():
        if ranking_rule.table not in tables:
            raise ValueError(f"semantic frequency ranking {name} references unknown table")
        if _qualified(ranking_rule.table, ranking_rule.dimension_column) not in columns:
            raise ValueError(f"semantic frequency ranking {name} references unknown column")


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
    *,
    metrics: Sequence[tuple[str, MetricRule]] = (),
    entities: Sequence[tuple[str, EntityRule]] = (),
) -> bool:
    for marker in _UNSUPPORTED_SCALAR_MARKERS:
        if marker not in question:
            continue
        if not any(
            marker.strip() in _normalize(alias) and _contains_alias(question, alias)
            for _, rule in matched_rules
            for alias in rule.aliases
        ) and not _grain_qualifier_is_proven(marker, metrics, entities):
            return True
    return False


def _grain_qualifier_is_proven(
    marker: str,
    metrics: Sequence[tuple[str, MetricRule]],
    entities: Sequence[tuple[str, EntityRule]],
) -> bool:
    """Accept a per-entity scalar only when metric grain carries that entity identity."""
    if marker.strip() not in {"per", "each", "mỗi"} or len(metrics) != 1 or len(entities) != 1:
        return False
    identity = entities[0][1].identity_column
    if identity is None:
        return False
    return _normalize(identity) in _normalize(metrics[0][1].source_grain)


def _infer_typed_frequency_ranking(
    decomposition: DecomposedQuestion,
    entities: Sequence[tuple[str, EntityRule]],
    catalog: CatalogSnapshot,
) -> FrequencyRankingSpec | None:
    """Infer row frequency from an unambiguous entity/dimension/ranking shape."""
    if (
        len(entities) != 1
        or len(decomposition.dimension_hints) != 1
        or decomposition.metric_hints
        or decomposition.limit_hint is None
        or not decomposition.sort_hints
        or decomposition.filter_hints
        or decomposition.time_hints
        or decomposition.set_operation_hint is not None
    ):
        return None
    entity_name, entity = entities[0]
    table = next((item for item in catalog.tables if item.name == entity.table), None)
    if table is None:
        return None
    dimension = _normalize(decomposition.dimension_hints[0]).replace(" ", "_")
    columns = [column.name for column in table.columns if _normalize(column.name) == dimension]
    if len(columns) != 1:
        return None
    return FrequencyRankingSpec(
        table=entity.table,
        dimension_column=columns[0],
        evidence_id=f"semantic.inferred_frequency.{entity_name}.{columns[0]}",
        source_grain=entity.row_grain,
        limit=decomposition.limit_hint,
    )


def _requested_metric_operators(question: str) -> tuple[AggregateOperator, ...]:
    return tuple(
        operator
        for operator, markers in _METRIC_OPERATOR_MARKERS.items()
        if any(_contains_alias(question, marker) for marker in markers)
    )


def _asks_row_count(
    question: str,
    requested_operators: tuple[AggregateOperator, ...],
) -> bool:
    """Separate row-count questions from scalar AVG/MIN/MAX phrased with “how much/many”."""
    has_count_language = any(marker in question for marker in _COUNT_MARKERS)
    has_scalar_operator = any(
        operator in {AggregateOperator.AVG, AggregateOperator.MIN, AggregateOperator.MAX}
        for operator in requested_operators
    )
    return has_count_language and not has_scalar_operator


def _entity_dimension_hints(
    decomposition: DecomposedQuestion,
    entities: Sequence[tuple[str, EntityRule]],
) -> list[str]:
    entity_names = {name.removesuffix("s") for name, _ in entities}
    return [
        hint
        for hint in decomposition.dimension_hints
        if _normalize(hint).removesuffix("s") not in entity_names
    ]


def _resolve_owned_dimension_column(
    decomposition: DecomposedQuestion,
    entities: Sequence[tuple[str, EntityRule]],
    catalog: CatalogSnapshot,
) -> str | None:
    """Resolve one named dimension to one column owned by the selected entity table."""
    hints = _entity_dimension_hints(decomposition, entities)
    if len(entities) != 1 or len(hints) != 1:
        return None
    table_name = entities[0][1].table
    table = next((item for item in catalog.tables if item.name == table_name), None)
    if table is None:
        return None
    hint = _normalize(hints[0]).removesuffix("s")
    matches = [
        column.name
        for column in table.columns
        if (normalized := _normalize(column.name.replace("_", " "))).removesuffix("s") == hint
        or normalized.split()[-1].removesuffix("s") == hint
    ]
    return matches[0] if len(matches) == 1 else None


def _requested_rounding_digits(question: str) -> int | None:
    matches = [
        int(match.group(1)) for pattern in _ROUNDING_PATTERNS if (match := pattern.search(question))
    ]
    return matches[0] if len(set(matches)) == 1 else None


def _numeric_equality_value(question: str) -> int | float | None:
    matches = [
        match.group(1)
        for pattern in _NUMERIC_EQUALITY_PATTERNS
        if (match := pattern.search(question))
    ]
    if len(set(matches)) != 1:
        return None
    raw = matches[0]
    if raw in _NUMBER_WORDS:
        return _NUMBER_WORDS[raw]
    value = float(raw)
    return int(value) if value.is_integer() else value


def _catalog_predicate(
    question: str,
    name: str,
    rule: PredicateRule,
) -> tuple[PredicateSpec | None, str | None]:
    if rule.kind == "null":
        asks_null = any(pattern.search(question) for pattern in _NULL_MARKERS)
        asks_not_null = any(pattern.search(question) for pattern in _NOT_NULL_MARKERS)
        if asks_null and asks_not_null:
            return None, f"AMBIGUOUS_NULL_PREDICATE:{name}"
        if not asks_null and not asks_not_null:
            return None, None
        return (
            PredicateSpec(
                table=rule.table,
                column=rule.column,
                operator=(
                    ComparisonOperator.IS_NOT_NULL if asks_not_null else ComparisonOperator.IS_NULL
                ),
                value=None,
                evidence_id=f"semantic.predicate.{name}",
            ),
            None,
        )
    value = _numeric_equality_value(question)
    if value is None:
        return None, None
    if rule.minimum is None or rule.maximum is None or not rule.minimum <= value <= rule.maximum:
        return None, f"PREDICATE_VALUE_OUT_OF_RANGE:{name}"
    return (
        PredicateSpec(
            table=rule.table,
            column=rule.column,
            operator=ComparisonOperator.EQ,
            value=value,
            evidence_id=f"semantic.predicate.{name}",
        ),
        None,
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


def _first_alias_span(question: str, aliases: Sequence[str]) -> tuple[int, int, str] | None:
    matches: list[tuple[int, int, str]] = []
    for alias in aliases:
        normalized = _normalize(alias)
        match = re.search(rf"(?<!\w){re.escape(normalized)}(?!\w)", question)
        if match is not None:
            matches.append((match.start(), match.end(), normalized))
    return min(matches, default=None, key=lambda item: (item[0], -len(item[2])))


def _join_spec(name: str, rule: JoinRule, *, reverse: bool = False) -> JoinSpec:
    left = ColumnRef(table=rule.left_table, column=rule.left_column)
    right = ColumnRef(table=rule.right_table, column=rule.right_column)
    if reverse:
        left, right = right, left
    return JoinSpec(
        left=left,
        right=right,
        kind=JoinKind.INNER,
        cardinality=rule.cardinality,
        evidence_id=f"semantic.join.{name}",
    )


def _safe_join_path(
    start: str,
    target: str,
    semantic_catalog: SemanticCatalog,
) -> tuple[JoinSpec, ...] | None:
    """Find a path that preserves rows at the current left-hand grain."""
    if start == target:
        return ()
    adjacency: dict[str, list[tuple[str, JoinSpec]]] = {}
    for name, rule in semantic_catalog.joins.items():
        adjacency.setdefault(rule.left_table, []).append((rule.right_table, _join_spec(name, rule)))
        if rule.cardinality is JoinCardinality.ONE_TO_ONE:
            adjacency.setdefault(rule.right_table, []).append(
                (rule.left_table, _join_spec(name, rule, reverse=True))
            )
    queue: deque[tuple[str, tuple[JoinSpec, ...]]] = deque([(start, ())])
    seen = {start}
    while queue:
        table, path = queue.popleft()
        for neighbor, join in adjacency.get(table, ()):
            if neighbor in seen:
                continue
            candidate = (*path, join)
            if neighbor == target:
                return candidate
            seen.add(neighbor)
            queue.append((neighbor, candidate))
    return None


def _metric_sources(rule: MetricRule) -> tuple[MetricSourceRule, ...]:
    primary = (
        ()
        if rule.column is None
        else (
            MetricSourceRule(
                table=rule.table,
                column=rule.column,
                source_grain=rule.source_grain,
                weight_column=rule.weight_column,
            ),
        )
    )
    return (*primary, *rule.alternate_sources)


def _required_columns_for_relational_binding(
    aggregate: AggregateSpec,
    joins: Sequence[JoinSpec],
    comparisons: Sequence[ColumnComparisonSpec] = (),
    grouping: GroupedAggregateSpec | None = None,
) -> tuple[str, ...]:
    columns: list[str] = []
    if aggregate.column is not None:
        columns.append(_qualified(aggregate.table, aggregate.column))
    if aggregate.weight_column is not None:
        columns.append(_qualified(aggregate.table, aggregate.weight_column))
    for join in joins:
        columns.extend(
            (
                _qualified(join.left.table, join.left.column),
                _qualified(join.right.table, join.right.column),
            )
        )
    for comparison in comparisons:
        columns.extend(
            (
                _qualified(comparison.left.table, comparison.left.column),
                _qualified(comparison.right.table, comparison.right.column),
            )
        )
    if grouping is not None:
        columns.append(_qualified(grouping.dimension.table, grouping.dimension.column))
        columns.extend(_qualified(item.table, item.column) for item in grouping.fallback_columns)
    return tuple(dict.fromkeys(columns))


def _grouped_aggregate_binding(
    normalized: str,
    decomposition: DecomposedQuestion,
    catalog: CatalogSnapshot,
    semantic_catalog: SemanticCatalog,
    metrics: Sequence[tuple[str, MetricRule]],
) -> SemanticBinding | None:
    dimensions = _matched_rules(normalized, semantic_catalog.dimensions)
    if (
        len(metrics) != 1
        or len(dimensions) != 1
        or decomposition.limit_hint is None
        or not decomposition.sort_hints
        or decomposition.filter_hints
        or decomposition.time_hints
        or decomposition.set_operation_hint is not None
    ):
        return None
    metric_name, metric = metrics[0]
    dimension_name, dimension = dimensions[0]
    requested = _requested_metric_operators(normalized)
    operator = requested[0] if len(requested) == 1 else metric.operator
    allowed = metric.allowed_operators or (metric.operator,)
    if len(requested) > 1 or operator not in allowed:
        return None
    selected: tuple[MetricSourceRule, tuple[JoinSpec, ...]] | None = None
    for source in _metric_sources(metric):
        path = _safe_join_path(source.table, dimension.table, semantic_catalog)
        if path is not None:
            selected = (source, path)
            break
    if selected is None:
        return None
    source, joins = selected
    aggregate = AggregateSpec(
        operator=operator,
        table=source.table,
        column=source.column,
        evidence_id=f"semantic.metric.{metric_name}",
        source_grain=source.source_grain,
        weight_column=source.weight_column if operator is AggregateOperator.AVG else None,
    )
    grouping = GroupedAggregateSpec(
        dimension=ColumnRef(table=dimension.table, column=dimension.column),
        fallback_columns=tuple(
            ColumnRef(table=dimension.table, column=column) for column in dimension.fallback_columns
        ),
        null_fallback=dimension.null_fallback,
        limit=decomposition.limit_hint,
    )
    tables = tuple(
        dict.fromkeys(
            [
                source.table,
                *(join.right.table for join in joins),
                dimension.table,
            ]
        )
    )
    return SemanticBinding(
        db_id=catalog.db_id,
        catalog_hash=catalog.catalog_hash,
        status=BindingStatus.PROVEN,
        aggregate=aggregate,
        joins=joins,
        grouped_aggregate=grouping,
        required_tables=tables,
        required_columns=_required_columns_for_relational_binding(
            aggregate, joins, grouping=grouping
        ),
        rule_ids=(
            f"metric.{metric_name}",
            f"dimension.{dimension_name}",
            *(join.evidence_id for join in joins),
        ),
    )


def _metric_comparison_binding(
    normalized: str,
    decomposition: DecomposedQuestion,
    catalog: CatalogSnapshot,
    semantic_catalog: SemanticCatalog,
    metrics: Sequence[tuple[str, MetricRule]],
    *,
    asks_count: bool,
) -> SemanticBinding | None:
    if (
        len(metrics) != 2
        or not asks_count
        or decomposition.dimension_hints
        or decomposition.sort_hints
        or decomposition.limit_hint is not None
        or decomposition.time_hints
        or decomposition.set_operation_hint is not None
    ):
        return None
    positioned = []
    for name, rule in metrics:
        span = _first_alias_span(normalized, rule.aliases)
        if span is None:
            return None
        positioned.append((span, name, rule))
    positioned.sort(key=lambda item: item[0][0])
    (left_span, left_name, left_rule), (right_span, right_name, right_rule) = positioned
    between = normalized[left_span[1] : right_span[0]]
    operators = [
        operator for pattern, operator in _METRIC_COMPARISON_OPERATORS if pattern.search(between)
    ]
    if len(operators) != 1:
        return None
    left_sources = _metric_sources(left_rule)
    right_sources = _metric_sources(right_rule)
    selected: tuple[MetricSourceRule, MetricSourceRule, tuple[JoinSpec, ...]] | None = None
    for left_source in left_sources:
        for right_source in right_sources:
            path = _safe_join_path(left_source.table, right_source.table, semantic_catalog)
            if path is not None:
                selected = (left_source, right_source, path)
                break
        if selected is not None:
            break
    if selected is None:
        return None
    left_source, right_source, joins = selected
    aggregate = AggregateSpec(
        operator=AggregateOperator.COUNT_ROWS,
        table=left_source.table,
        evidence_id="semantic.relational.count_rows",
        source_grain=left_source.source_grain,
    )
    comparison = ColumnComparisonSpec(
        left=ColumnRef(table=left_source.table, column=left_source.column),
        operator=operators[0],
        right=ColumnRef(table=right_source.table, column=right_source.column),
        evidence_id=f"semantic.comparison.{left_name}.{right_name}",
    )
    tables = tuple(
        dict.fromkeys(
            [left_source.table, *(join.right.table for join in joins), right_source.table]
        )
    )
    return SemanticBinding(
        db_id=catalog.db_id,
        catalog_hash=catalog.catalog_hash,
        status=BindingStatus.PROVEN,
        aggregate=aggregate,
        joins=joins,
        column_comparisons=(comparison,),
        required_tables=tables,
        required_columns=_required_columns_for_relational_binding(aggregate, joins, (comparison,)),
        rule_ids=(
            f"metric.{left_name}",
            f"metric.{right_name}",
            comparison.evidence_id,
            *(join.evidence_id for join in joins),
        ),
    )


def _intersection_binding(
    normalized: str,
    decomposition: DecomposedQuestion,
    catalog: CatalogSnapshot,
    semantic_catalog: SemanticCatalog,
    entities: Sequence[tuple[str, EntityRule]],
    *,
    asks_count: bool,
) -> SemanticBinding | None:
    if (
        not asks_count
        or not any(marker in normalized for marker in _INTERSECTION_MARKERS)
        or decomposition.dimension_hints
        or decomposition.sort_hints
        or decomposition.limit_hint is not None
        or decomposition.time_hints
        or decomposition.set_operation_hint is not None
    ):
        return None
    matched: list[tuple[int, int, int, str, EntityRule]] = []
    for name, rule in entities:
        span = _first_alias_span(normalized, rule.aliases)
        if span is not None and len(span[2].split()) >= 2:
            matched.append((span[0], span[1], len(span[2].split()), name, rule))
    specific = [
        item
        for item in matched
        if not any(
            other[0] <= item[0] and item[1] <= other[1] and other[2] > item[2] for other in matched
        )
    ]
    specific.sort(key=lambda item: item[0])
    if len(specific) < 2:
        return None
    _, _, _, base_name, base = specific[0]
    joins: list[JoinSpec] = []
    current_tables = {base.table}
    for _, _, _, _, target in specific[1:]:
        path = next(
            (
                candidate
                for start in sorted(current_tables)
                if (candidate := _safe_join_path(start, target.table, semantic_catalog)) is not None
            ),
            None,
        )
        if path is None:
            return None
        joins.extend(path)
        current_tables.update(
            table for join in path for table in (join.left.table, join.right.table)
        )
    joins = list(dict.fromkeys(joins))
    aggregate = AggregateSpec(
        operator=AggregateOperator.COUNT_ROWS,
        table=base.table,
        evidence_id=f"semantic.entity.{base_name}",
        source_grain=base.row_grain,
    )
    tables = tuple(dict.fromkeys([base.table, *(join.right.table for join in joins)]))
    return SemanticBinding(
        db_id=catalog.db_id,
        catalog_hash=catalog.catalog_hash,
        status=BindingStatus.PROVEN,
        aggregate=aggregate,
        joins=tuple(joins),
        required_tables=tables,
        required_columns=_required_columns_for_relational_binding(aggregate, joins),
        rule_ids=(
            *(f"entity.{name}" for _, _, _, name, _ in specific),
            *(join.evidence_id for join in joins),
        ),
    )


def _anti_join_binding(
    normalized: str,
    decomposition: DecomposedQuestion,
    catalog: CatalogSnapshot,
    semantic_catalog: SemanticCatalog,
    entities: Sequence[tuple[str, EntityRule]],
    *,
    asks_count: bool,
) -> SemanticBinding | None:
    """Prove COUNT(base) where a declared one-to-one child row is absent."""
    markers = [match for pattern in _ANTI_JOIN_PATTERNS if (match := pattern.search(normalized))]
    if (
        not asks_count
        or len(markers) != 1
        or decomposition.sort_hints
        or decomposition.limit_hint is not None
        or decomposition.time_hints
        or decomposition.set_operation_hint is not None
    ):
        return None
    marker = markers[0]
    matched: list[tuple[int, int, int, str, EntityRule]] = []
    for name, rule in entities:
        span = _first_alias_span(normalized, rule.aliases)
        if span is not None:
            matched.append((span[0], span[1], len(span[2].split()), name, rule))
    specific = [
        item
        for item in matched
        if not any(
            other[0] <= item[0] and item[1] <= other[1] and other[2] > item[2] for other in matched
        )
    ]
    left = [item for item in specific if item[1] <= marker.start()]
    right = [item for item in specific if item[0] >= marker.end()]
    if len(left) != 1 or len(right) != 1:
        return None
    _, _, _, base_name, base = left[0]
    _, _, _, missing_name, missing = right[0]
    direct = [
        (name, rule)
        for name, rule in semantic_catalog.joins.items()
        if rule.left_table == base.table
        and rule.right_table == missing.table
        and rule.cardinality is JoinCardinality.ONE_TO_ONE
    ]
    if len(direct) != 1:
        return None
    join_name, join_rule = direct[0]
    join = _join_spec(join_name, join_rule).model_copy(update={"kind": JoinKind.LEFT})
    predicate = PredicateSpec(
        table=missing.table,
        column=join.right.column,
        operator=ComparisonOperator.IS_NULL,
        value=None,
        evidence_id=f"semantic.anti_join.{join_name}",
    )
    aggregate = AggregateSpec(
        operator=AggregateOperator.COUNT_ROWS,
        table=base.table,
        evidence_id=f"semantic.entity.{base_name}",
        source_grain=base.row_grain,
    )
    required_columns = (
        *_required_columns_for_relational_binding(aggregate, (join,)),
        _qualified(predicate.table, predicate.column),
    )
    return SemanticBinding(
        db_id=catalog.db_id,
        catalog_hash=catalog.catalog_hash,
        status=BindingStatus.PROVEN,
        aggregate=aggregate,
        predicates=(predicate,),
        joins=(join,),
        required_tables=(base.table, missing.table),
        required_columns=tuple(dict.fromkeys(required_columns)),
        rule_ids=(
            f"entity.{base_name}",
            f"entity.{missing_name}",
            join.evidence_id,
            predicate.evidence_id,
        ),
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
    frequency_rankings = _matched_rules(normalized, semantic_catalog.frequency_rankings)
    derived = _matched_rules(normalized, semantic_catalog.derived)
    metrics = _matched_rules(normalized, semantic_catalog.metrics)
    entities = _matched_rules(normalized, semantic_catalog.entities)
    requested_operators = _requested_metric_operators(normalized)
    asks_count = _asks_row_count(normalized, requested_operators)
    asks_distinct = any(marker in normalized for marker in _DISTINCT_MARKERS)
    owned_dimension = (
        _resolve_owned_dimension_column(decomposition, entities, catalog)
        if asks_count and asks_distinct
        else None
    )
    if len(frequency_rankings) > 1:
        return SemanticBinding(
            db_id=catalog.db_id,
            catalog_hash=catalog.catalog_hash,
            status=BindingStatus.AMBIGUOUS,
            reasons=("MULTIPLE_FREQUENCY_RANKINGS",),
        )
    if len(frequency_rankings) == 1:
        name, rule = frequency_rankings[0]
        ranking = FrequencyRankingSpec(
            table=rule.table,
            dimension_column=rule.dimension_column,
            evidence_id=f"semantic.frequency_ranking.{name}",
            source_grain=rule.source_grain,
            limit=decomposition.limit_hint or 1,
        )
        ranking_reasons: list[str] = []
        if decomposition.filter_hints or decomposition.time_hints:
            ranking_reasons.append("FILTERED_FREQUENCY_RANKING_UNSUPPORTED")
        if decomposition.set_operation_hint is not None:
            ranking_reasons.append("SET_FREQUENCY_RANKING_UNSUPPORTED")
        return SemanticBinding(
            db_id=catalog.db_id,
            catalog_hash=catalog.catalog_hash,
            status=(BindingStatus.PROVEN if not ranking_reasons else BindingStatus.INCOMPLETE),
            frequency_ranking=ranking,
            required_tables=(rule.table,),
            required_columns=(_qualified(rule.table, rule.dimension_column),),
            rule_ids=(f"frequency_ranking.{name}",),
            reasons=tuple(ranking_reasons),
        )
    inferred_ranking = _infer_typed_frequency_ranking(decomposition, entities, catalog)
    if inferred_ranking is not None:
        return SemanticBinding(
            db_id=catalog.db_id,
            catalog_hash=catalog.catalog_hash,
            status=BindingStatus.PROVEN,
            frequency_ranking=inferred_ranking,
            required_tables=(inferred_ranking.table,),
            required_columns=(
                _qualified(inferred_ranking.table, inferred_ranking.dimension_column),
            ),
            rule_ids=("inferred.frequency_ranking",),
        )
    grouped = _grouped_aggregate_binding(
        normalized,
        decomposition,
        catalog,
        semantic_catalog,
        metrics,
    )
    if grouped is not None:
        return grouped
    metric_comparison = _metric_comparison_binding(
        normalized,
        decomposition,
        catalog,
        semantic_catalog,
        metrics,
        asks_count=asks_count,
    )
    if metric_comparison is not None:
        return metric_comparison
    anti_join = _anti_join_binding(
        normalized,
        decomposition,
        catalog,
        semantic_catalog,
        entities,
        asks_count=asks_count,
    )
    if anti_join is not None:
        return anti_join
    intersection = _intersection_binding(
        normalized,
        decomposition,
        catalog,
        semantic_catalog,
        entities,
        asks_count=asks_count,
    )
    if intersection is not None:
        return intersection
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
            and not (asks_count and asks_distinct and owned_dimension is not None)
            and not dimensions_are_rule_semantics
            and not derived_operator_is_explicit
        )
        or decomposition.sort_hints
        or decomposition.limit_hint is not None
        or decomposition.time_hints
        or decomposition.set_operation_hint is not None
        or _unresolved_shape_marker(
            normalized,
            [*derived, *metrics],
            metrics=metrics,
            entities=entities,
        )
    )
    if len(derived) > 1:
        return SemanticBinding(
            db_id=catalog.db_id,
            catalog_hash=catalog.catalog_hash,
            status=BindingStatus.AMBIGUOUS,
            reasons=("MULTIPLE_DERIVED_RULES",),
        )
    if len(derived) == 1 and not metrics and scalar_shape and derived_operator_is_explicit:
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
        allowed_operators = metric_rule.allowed_operators or (metric_rule.operator,)
        selected_operator = (
            requested_operators[0] if len(requested_operators) == 1 else metric_rule.operator
        )
        count_marker_is_metric_phrase = any(
            marker.strip() in _normalize(alias) and _contains_alias(normalized, alias)
            for marker in _COUNT_MARKERS
            for alias in metric_rule.aliases
        )
        if len(requested_operators) > 1:
            operator_reason = "MULTIPLE_AGGREGATE_OPERATORS"
        elif selected_operator not in allowed_operators:
            operator_reason = "AGGREGATE_OPERATOR_NOT_ALLOWED"
        elif asks_count and not count_marker_is_metric_phrase:
            operator_reason = "COUNT_METRIC_CONFLICT"
        aggregate = AggregateSpec(
            operator=selected_operator,
            table=metric_rule.table,
            column=metric_rule.column,
            evidence_id=f"semantic.metric.{name}",
            source_grain=metric_rule.source_grain,
            weight_column=(
                metric_rule.weight_column if selected_operator is AggregateOperator.AVG else None
            ),
            rounding_digits=_requested_rounding_digits(normalized),
        )
        rule_ids.append(f"metric.{name}")
    elif len(entities) == 1 and asks_count:
        name, entity_rule = entities[0]
        explicit_columns = [
            column.name
            for table in catalog.tables
            if table.name == entity_rule.table
            for column in table.columns
            if _contains_alias(normalized, column.name)
        ]
        distinct = asks_distinct
        identity = (
            explicit_columns[0]
            if len(explicit_columns) == 1
            else owned_dimension
            if owned_dimension is not None
            else entity_rule.identity_column
        )
        if (
            distinct
            and _entity_dimension_hints(decomposition, entities)
            and owned_dimension is None
        ):
            return SemanticBinding(
                db_id=catalog.db_id,
                catalog_hash=catalog.catalog_hash,
                status=BindingStatus.INCOMPLETE,
                reasons=("DISTINCT_DIMENSION_UNRESOLVED",),
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
            source_grain=entity_rule.row_grain,
        )
        rule_ids.append(f"entity.{name}")
        if distinct and owned_dimension is not None:
            rule_ids.append(f"schema.dimension.{entity_rule.table}.{owned_dimension}")

    predicates: list[PredicateSpec] = []
    # A derived rule may describe the population while a metric rule describes the value over
    # that population. Compose them only when both have the same physical owner; this prevents a
    # generic derived COUNT from overriding an explicitly requested AVG/MAX metric.
    if len(metrics) == 1 and len(derived) == 1:
        derived_name, derived_rule = derived[0]
        if aggregate is not None and aggregate.table == derived_rule.aggregate.table:
            predicates.extend(derived_rule.predicates)
            rule_ids.append(f"derived.{derived_name}")
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
    matched_predicate_rules = _matched_rules(normalized, semantic_catalog.predicate_rules)
    predicate_rule_reasons: list[str] = []
    resolved_catalog_predicates: list[tuple[str, PredicateSpec]] = []
    for predicate_name, predicate_rule in matched_predicate_rules:
        predicate, reason = _catalog_predicate(normalized, predicate_name, predicate_rule)
        if reason is not None:
            predicate_rule_reasons.append(reason)
        if predicate is not None:
            resolved_catalog_predicates.append((predicate_name, predicate))
    if len(resolved_catalog_predicates) > 1:
        return SemanticBinding(
            db_id=catalog.db_id,
            catalog_hash=catalog.catalog_hash,
            status=BindingStatus.AMBIGUOUS,
            reasons=("MULTIPLE_CATALOG_PREDICATES",),
        )
    for name, predicate in resolved_catalog_predicates:
        predicates.append(predicate)
        rule_ids.append(f"predicate.{name}")

    reasons: list[str] = []
    if not scalar_shape:
        reasons.append("NON_SCALAR_SHAPE")
    if aggregate is None:
        reasons.append("AGGREGATE_UNRESOLVED")
    if decomposition.filter_hints and not predicates:
        reasons.append("FILTER_UNRESOLVED")
    if operator_reason is not None:
        reasons.append(operator_reason)
    reasons.extend(predicate_rule_reasons)
    selected_derived = any(rule_id.startswith("derived.") for rule_id in rule_ids)
    asks_null = any(pattern.search(normalized) for pattern in _NULL_MARKERS)
    asks_not_null = any(pattern.search(normalized) for pattern in _NOT_NULL_MARKERS)
    if asks_null and not any(
        predicate.operator is ComparisonOperator.IS_NULL for predicate in predicates
    ):
        reasons.append("NULL_PREDICATE_UNRESOLVED")
    if asks_not_null and not any(
        predicate.operator is ComparisonOperator.IS_NOT_NULL for predicate in predicates
    ):
        reasons.append("NOT_NULL_PREDICATE_UNRESOLVED")
    if (
        any(pattern.search(normalized) for pattern in _ORDERED_COMPARISON_PATTERNS)
        and not selected_derived
        and not any(
            predicate.operator
            in {
                ComparisonOperator.GT,
                ComparisonOperator.GTE,
                ComparisonOperator.LT,
                ComparisonOperator.LTE,
            }
            for predicate in predicates
        )
    ):
        reasons.append("ORDERED_COMPARISON_UNRESOLVED")
    if (
        any(pattern.search(normalized) for pattern in _EXACT_COMPARISON_PATTERNS)
        and not selected_derived
        and not any(predicate.operator is ComparisonOperator.EQ for predicate in predicates)
    ):
        reasons.append("EXACT_COMPARISON_UNRESOLVED")
    if (
        any(pattern.search(normalized) for pattern in _COLUMN_COMPARISON_PATTERNS)
        and not selected_derived
    ):
        reasons.append("COLUMN_COMPARISON_UNRESOLVED")
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
        *(
            [_qualified(aggregate.table, aggregate.weight_column)]
            if aggregate is not None and aggregate.weight_column is not None
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
