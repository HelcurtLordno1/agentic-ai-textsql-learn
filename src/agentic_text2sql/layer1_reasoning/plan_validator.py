"""Gold-blind consistency gate for the DIN-SQL clause plan."""

from __future__ import annotations

import re
from collections import deque

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import (
    ComplexityKind,
    DINSQLPlan,
    JoinStep,
    PlanningStrategy,
    PlanValidationReport,
)
from agentic_text2sql.contracts.retrieval import SchemaContext
from agentic_text2sql.layer2_grounding.fk_graph import catalog_join_edges

_QUALIFIED = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")
_EQUALITY = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\b"
)


def _catalog_identifiers(catalog: CatalogSnapshot) -> tuple[set[str], set[str]]:
    tables = {table.name for table in catalog.tables}
    columns = {
        f"{table.name}.{column.name}" for table in catalog.tables for column in table.columns
    }
    return tables, columns


def _allowed_fk_pairs(catalog: CatalogSnapshot) -> set[frozenset[str]]:
    return {
        frozenset(part.strip() for part in equality.split(" = ", maxsplit=1))
        for _, _, join, _ in catalog_join_edges(catalog)
        for equality in join.split(" AND ")
    }


def _clause_text(plan: DINSQLPlan) -> list[str]:
    return [
        *plan.clauses.select,
        *plan.clauses.where,
        *plan.clauses.group_by,
        *plan.clauses.having,
        *plan.clauses.order_by,
        *(join.condition for join in plan.clauses.joins),
        *(
            text
            for step in plan.clauses.subqueries
            for text in [
                *step.select,
                *step.where,
                *step.group_by,
                *step.having,
                *(join.condition for join in step.joins),
            ]
        ),
    ]


def _tables_are_connected(required: set[str], joins: list[JoinStep]) -> bool:
    if len(required) < 2:
        return True
    adjacency: dict[str, set[str]] = {table: set() for table in required}
    for join in joins:
        adjacency.setdefault(join.left_table, set()).add(join.right_table)
        adjacency.setdefault(join.right_table, set()).add(join.left_table)
    start = next(iter(required))
    seen = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for neighbor in sorted(adjacency.get(node, ())):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return required <= seen


def validate_plan(
    plan: DINSQLPlan,
    catalog: CatalogSnapshot,
    schema_context: SchemaContext,
) -> PlanValidationReport:
    """Reject identifier invention, broken join paths, and clause-shape contradictions."""
    signals: list[str] = []
    tables, columns = _catalog_identifiers(catalog)
    context_tables = set(schema_context.selected_tables)
    planned_tables = set(plan.clauses.from_tables)
    all_planned_tables = planned_tables | {
        table for step in plan.clauses.subqueries for table in step.from_tables
    }

    if plan.semantic_links.catalog_hash != catalog.catalog_hash:
        signals.append("CATALOG_IDENTITY_MISMATCH")
    if all_planned_tables - tables:
        signals.append("UNKNOWN_PLAN_TABLE")
    if all_planned_tables - context_tables:
        signals.append("TABLE_OUTSIDE_EVIDENCE")

    qualified = {
        f"{table}.{column}"
        for text in _clause_text(plan)
        for table, column in _QUALIFIED.findall(text)
    }
    if qualified - columns:
        signals.append("UNKNOWN_PLAN_COLUMN")
    visible_columns = set(schema_context.selected_columns) | {
        f"{table.name}.{column.name}"
        for table in catalog.tables
        if table.name in context_tables
        for column in table.columns
        if column.primary_key_position > 0
    }
    if qualified - visible_columns:
        signals.append("COLUMN_OUTSIDE_EVIDENCE")
    if {value.split(".", maxsplit=1)[0] for value in qualified} - all_planned_tables:
        signals.append("COLUMN_OWNER_NOT_IN_FROM")

    required_owners = set(plan.semantic_links.required_tables)
    if plan.semantic_links.population_owner is not None:
        required_owners.add(plan.semantic_links.population_owner)
    if required_owners - all_planned_tables:
        signals.append("SEMANTIC_OWNER_MISSING")

    allowed_pairs = _allowed_fk_pairs(catalog)
    all_joins = [
        *plan.clauses.joins,
        *(join for step in plan.clauses.subqueries for join in step.joins),
    ]
    for join in all_joins:
        if {join.left_table, join.right_table} - all_planned_tables:
            signals.append("JOIN_ENDPOINT_OUTSIDE_FROM")
        equalities = [frozenset(pair) for pair in _EQUALITY.findall(join.condition)]
        if not equalities or any(pair not in allowed_pairs for pair in equalities):
            signals.append("UNDECLARED_JOIN_CONDITION")
    if len(planned_tables) > 1 and not plan.clauses.joins:
        signals.append("JOIN_PATH_MISSING")
    elif not _tables_are_connected(planned_tables, list(plan.clauses.joins)):
        signals.append("JOIN_PATH_DISCONNECTED")
    for step in plan.clauses.subqueries:
        step_tables = set(step.from_tables)
        if len(step_tables) > 1 and not step.joins:
            signals.append("SUBQUERY_JOIN_PATH_MISSING")
        elif not _tables_are_connected(step_tables, list(step.joins)):
            signals.append("SUBQUERY_JOIN_PATH_DISCONNECTED")

    step_ids = [step.step_id for step in plan.clauses.subqueries]
    if len(step_ids) != len(set(step_ids)):
        signals.append("DUPLICATE_SUBQUERY_ID")
    known_steps: set[str] = set()
    for step in plan.clauses.subqueries:
        if set(step.depends_on) - known_steps:
            signals.append("SUBQUERY_DEPENDENCY_NOT_PRIOR")
        known_steps.add(step.step_id)

    if plan.limit != plan.clauses.limit:
        signals.append("LIMIT_CONTRACT_MISMATCH")
    if plan.task_type == "aggregation" and not plan.dimensions:
        if plan.clauses.output_grain.casefold() != "one scalar row":
            signals.append("SCALAR_OUTPUT_GRAIN_MISMATCH")
        if plan.clauses.order_by or plan.clauses.limit is not None:
            signals.append("SCALAR_AS_RANKING")
    if plan.task_type == "ranking":
        if not plan.clauses.order_by:
            signals.append("RANKING_ORDER_MISSING")
        if plan.limit is not None and plan.clauses.limit != plan.limit:
            signals.append("RANKING_LIMIT_MISMATCH")

    clause_text = " ".join(_clause_text(plan)).casefold()
    has_nested = bool(plan.clauses.subqueries or plan.clauses.set_operation) or any(
        marker in clause_text for marker in (" window ", "over(", "over (")
    )
    has_join = bool(plan.clauses.joins or len(planned_tables) > 1)
    if has_nested:
        expected_kind = ComplexityKind.NESTED_SET_WINDOW
        expected_strategy = PlanningStrategy.NESTED
    elif has_join:
        expected_kind = ComplexityKind.MULTI_JOIN
        expected_strategy = PlanningStrategy.NON_NESTED
    elif plan.task_type in {"aggregation", "ranking"}:
        expected_kind = ComplexityKind.AGGREGATE
        expected_strategy = PlanningStrategy.EASY
    else:
        expected_kind = ComplexityKind.SIMPLE
        expected_strategy = PlanningStrategy.EASY
    if plan.complexity.kind is not expected_kind:
        signals.append("COMPLEXITY_KIND_MISMATCH")
    if plan.complexity.strategy is not expected_strategy:
        signals.append("PLANNING_STRATEGY_MISMATCH")

    unique_signals = tuple(dict.fromkeys(signals))
    return PlanValidationReport(
        accepted=not unique_signals,
        signals=unique_signals,
        safe_message=(
            None
            if not unique_signals
            else "DIN-SQL plan conflicts with catalog evidence or clause dependencies"
        ),
    )
