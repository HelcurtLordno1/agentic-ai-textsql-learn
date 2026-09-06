"""Gold-aware DIN-SQL planning metrics; this module is evaluator-only."""

from __future__ import annotations

import re
from typing import Any

from sqlglot import exp, parse_one

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import DINSQLPlan
from agentic_text2sql_eval.schema_metrics import extract_gold_schema

_QUALIFIED = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")
_EQUALITY = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\b"
)
CLAUSES = (
    "select",
    "from",
    "join",
    "where",
    "group_by",
    "having",
    "order_by",
    "limit",
    "subquery",
    "set_operation",
)


def _sql_presence(sql: str) -> dict[str, bool]:
    statement = parse_one(sql, read="sqlite")
    selects = list(statement.find_all(exp.Select))
    return {
        "select": bool(selects),
        "from": statement.find(exp.From) is not None,
        "join": statement.find(exp.Join) is not None,
        "where": statement.find(exp.Where) is not None,
        "group_by": statement.find(exp.Group) is not None,
        "having": statement.find(exp.Having) is not None,
        "order_by": statement.find(exp.Order) is not None,
        "limit": statement.find(exp.Limit) is not None,
        "subquery": len(selects) > 1 or statement.find(exp.Subquery) is not None,
        "set_operation": any(
            statement.find(kind) is not None for kind in (exp.Union, exp.Intersect, exp.Except)
        ),
    }


def _plan_presence(plan: DINSQLPlan) -> dict[str, bool]:
    clauses = plan.clauses
    return {
        "select": bool(clauses.select),
        "from": bool(clauses.from_tables),
        "join": bool(clauses.joins),
        "where": bool(clauses.where),
        "group_by": bool(clauses.group_by),
        "having": bool(clauses.having),
        "order_by": bool(clauses.order_by),
        "limit": clauses.limit is not None,
        "subquery": bool(clauses.subqueries),
        "set_operation": clauses.set_operation is not None,
    }


def _f1(predicted: set[str], expected: set[str]) -> dict[str, float | int]:
    true_positive = len(predicted & expected)
    false_positive = len(predicted - expected)
    false_negative = len(expected - predicted)
    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, true_positive + false_negative)
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / max(1e-12, precision + recall),
    }


def evaluate_plan(
    plan_payload: dict[str, Any],
    *,
    gold_sql: str,
    predicted_sql: str | None,
    catalog: CatalogSnapshot,
) -> dict[str, Any]:
    """Score clause detection and physical evidence without exposing gold to runtime."""
    plan = DINSQLPlan.model_validate(plan_payload)
    expected_presence = _sql_presence(gold_sql)
    planned_presence = _plan_presence(plan)
    expected_clauses = {name for name in CLAUSES if expected_presence[name]}
    planned_clauses = {name for name in CLAUSES if planned_presence[name]}

    gold_schema = extract_gold_schema(gold_sql, catalog)
    planned_tables = {table.casefold() for table in plan.clauses.from_tables}
    plan_text = " ".join(
        [
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
    )
    planned_columns = {
        f"{table.casefold()}.{column.casefold()}" for table, column in _QUALIFIED.findall(plan_text)
    }
    planned_joins = {
        frozenset({left.casefold(), right.casefold()})
        for join in [
            *plan.clauses.joins,
            *(join for step in plan.clauses.subqueries for join in step.joins),
        ]
        for left, right in _EQUALITY.findall(join.condition)
    }
    schema_metrics = {
        "table_recall": len(planned_tables & gold_schema.tables) / max(1, len(gold_schema.tables)),
        "table_precision": len(planned_tables & gold_schema.tables) / max(1, len(planned_tables)),
        "column_recall": (
            len(planned_columns & gold_schema.columns) / len(gold_schema.columns)
            if gold_schema.columns
            else None
        ),
        "join_recall": (
            len(planned_joins & gold_schema.join_edges) / len(gold_schema.join_edges)
            if gold_schema.join_edges
            else None
        ),
    }

    consistency: dict[str, Any] | None = None
    if predicted_sql is not None:
        sql_presence = _sql_presence(predicted_sql)
        generated_clauses = {name for name in CLAUSES if sql_presence[name]}
        generated_schema = extract_gold_schema(predicted_sql, catalog)
        consistency = {
            "clause_agreement": sum(
                planned_presence[name] == sql_presence[name] for name in CLAUSES
            )
            / len(CLAUSES),
            "planned_table_coverage": len(planned_tables & generated_schema.tables)
            / max(1, len(planned_tables)),
            "clause_f1": _f1(generated_clauses, planned_clauses),
        }
    return {
        "clause_f1": _f1(planned_clauses, expected_clauses),
        "clause_exact": planned_presence == expected_presence,
        "by_clause": {
            name: {
                "planned": planned_presence[name],
                "gold": expected_presence[name],
                "correct": planned_presence[name] == expected_presence[name],
            }
            for name in CLAUSES
        },
        "schema": schema_metrics,
        "plan_to_sql": consistency,
    }


def aggregate_plan_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Create macro planning diagnostics for an evaluated DIN-SQL slice."""
    if not rows:
        return {"evaluated_count": 0}

    def mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    plan_to_sql = [row["plan_to_sql"] for row in rows if row["plan_to_sql"] is not None]
    return {
        "evaluated_count": len(rows),
        "clause_exact_count": sum(bool(row["clause_exact"]) for row in rows),
        "clause_exact_rate": sum(bool(row["clause_exact"]) for row in rows) / len(rows),
        "macro_clause_f1": mean([float(row["clause_f1"]["f1"]) for row in rows]),
        "macro_table_recall": mean([float(row["schema"]["table_recall"]) for row in rows]),
        "macro_column_recall": mean(
            [
                float(row["schema"]["column_recall"])
                for row in rows
                if row["schema"]["column_recall"] is not None
            ]
        ),
        "macro_join_recall": mean(
            [
                float(row["schema"]["join_recall"])
                for row in rows
                if row["schema"]["join_recall"] is not None
            ]
        ),
        "macro_plan_to_sql_clause_agreement": mean(
            [float(row["clause_agreement"]) for row in plan_to_sql]
        ),
        "by_clause_accuracy": {
            name: sum(bool(row["by_clause"][name]["correct"]) for row in rows) / len(rows)
            for name in CLAUSES
        },
    }
