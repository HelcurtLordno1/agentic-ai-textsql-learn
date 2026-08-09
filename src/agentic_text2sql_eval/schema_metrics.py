"""Gold-aware schema retrieval metrics; never imported by runtime code."""

from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp, parse_one

from agentic_text2sql.contracts.retrieval import RetrievalResult


@dataclass(frozen=True)
class GoldSchema:
    tables: frozenset[str]
    columns: frozenset[str]
    foreign_keys: frozenset[frozenset[str]]


def extract_gold_schema(sql: str) -> GoldSchema:
    expression = parse_one(sql, read="sqlite")
    tables = frozenset(table.name for table in expression.find_all(exp.Table))
    columns = frozenset(
        column.name for column in expression.find_all(exp.Column) if column.name != "*"
    )
    aliases = {table.alias_or_name: table.name for table in expression.find_all(exp.Table)}
    joins: set[frozenset[str]] = set()
    for equality in expression.find_all(exp.EQ):
        if isinstance(equality.left, exp.Column) and isinstance(equality.right, exp.Column):
            left_table = aliases.get(equality.left.table, equality.left.table)
            right_table = aliases.get(equality.right.table, equality.right.table)
            if left_table and right_table and left_table != right_table:
                joins.add(
                    frozenset(
                        {
                            f"{left_table}.{equality.left.name}",
                            f"{right_table}.{equality.right.name}",
                        }
                    )
                )
    return GoldSchema(tables=tables, columns=columns, foreign_keys=frozenset(joins))


def score_retrieval(result: RetrievalResult, gold: GoldSchema) -> dict[str, float]:
    selected_tables = {item.document.table for item in result.candidates}
    selected_columns = {
        item.document.column for item in result.candidates if item.document.column is not None
    }
    table_hits = gold.tables & selected_tables
    column_hits = gold.columns & selected_columns
    retrieved_items = len(selected_tables) + len(selected_columns)
    gold_items = len(gold.tables) + len(gold.columns)
    selected_joins = {
        frozenset(pair.split("=", maxsplit=1))
        for item in result.candidates
        if item.document.kind == "relationship"
        for pair in item.document.neighbors
        if "=" in pair
    }
    return {
        "table_recall": len(table_hits) / max(1, len(gold.tables)),
        "column_recall": len(column_hits) / max(1, len(gold.columns)),
        "context_precision": (len(table_hits) + len(column_hits)) / max(1, retrieved_items),
        "schema_recall": (len(table_hits) + len(column_hits)) / max(1, gold_items),
        "foreign_key_recall": (
            len(gold.foreign_keys & selected_joins) / len(gold.foreign_keys)
            if gold.foreign_keys
            else 1.0
        ),
    }
