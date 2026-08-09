"""Qualified, gold-aware schema metrics; never imported by runtime code."""

from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp, parse_one
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import Scope, traverse_scope

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.retrieval import RetrievalResult, SchemaContext


@dataclass(frozen=True)
class GoldSchema:
    tables: frozenset[str]
    columns: frozenset[str]
    join_edges: frozenset[frozenset[str]]
    foreign_keys: frozenset[frozenset[str]]


def _catalog_schema(catalog: CatalogSnapshot) -> dict[str, dict[str, str]]:
    return {
        table.name: {column.name: column.data_type or "TEXT" for column in table.columns}
        for table in catalog.tables
    }


def _resolve_column(scope: Scope, column: exp.Column) -> str | None:
    source = scope.sources.get(column.table)
    if isinstance(source, exp.Table):
        return f"{source.name.casefold()}.{column.name.casefold()}"
    return None


def extract_gold_schema(sql: str, catalog: CatalogSnapshot) -> GoldSchema:
    schema = _catalog_schema(catalog)
    catalog_table_names = {name.casefold() for name in schema}
    expression = qualify(
        parse_one(sql, read="sqlite"),
        dialect="sqlite",
        schema=schema,
        validate_qualify_columns=False,
        identify=False,
    )
    tables = frozenset(
        table.name.casefold()
        for table in expression.find_all(exp.Table)
        if table.name.casefold() in catalog_table_names
    )
    columns: set[str] = set()
    joins: set[frozenset[str]] = set()
    for scope in traverse_scope(expression):
        for column in scope.columns:
            resolved = _resolve_column(scope, column)
            if resolved is not None:
                columns.add(resolved)
        for equality in scope.expression.find_all(exp.EQ):
            if isinstance(equality.left, exp.Column) and isinstance(equality.right, exp.Column):
                left = _resolve_column(scope, equality.left)
                right = _resolve_column(scope, equality.right)
                if left and right and left.split(".", 1)[0] != right.split(".", 1)[0]:
                    joins.add(frozenset({left, right}))
    declared_foreign_keys = {
        frozenset(
            {
                f"{table.name.casefold()}.{source.casefold()}",
                f"{foreign_key.target_table.casefold()}.{target.casefold()}",
            }
        )
        for table in catalog.tables
        for foreign_key in table.foreign_keys
        for source, target in zip(foreign_key.from_columns, foreign_key.target_columns, strict=True)
    }
    return GoldSchema(
        tables=tables,
        columns=frozenset(columns),
        join_edges=frozenset(joins),
        foreign_keys=frozenset(joins & declared_foreign_keys),
    )


def score_retrieval(
    result: RetrievalResult | SchemaContext, gold: GoldSchema
) -> dict[str, float | None]:
    if isinstance(result, RetrievalResult):
        selected_tables = {item.document.table.casefold() for item in result.candidates}
        selected_columns = {
            f"{item.document.table.casefold()}.{item.document.column.casefold()}"
            for item in result.candidates
            if item.document.column is not None
        }
        selected_joins = {
            frozenset(part.casefold() for part in pair.split("=", maxsplit=1))
            for item in result.candidates
            if item.document.kind == "relationship"
            for pair in item.document.neighbors
            if "=" in pair
        }
    else:
        selected_tables = {table.casefold() for table in result.selected_tables}
        selected_columns = {column.casefold() for column in result.selected_columns}
        selected_joins = {
            frozenset(part.strip().casefold() for part in equality.split(" = ", maxsplit=1))
            for join in result.joins
            for equality in join.split(" AND ")
            if " = " in equality
        }
    table_hits = gold.tables & selected_tables
    column_hits = gold.columns & selected_columns
    retrieved_items = len(selected_tables) + len(selected_columns)
    gold_items = len(gold.tables) + len(gold.columns)
    return {
        "table_recall": len(table_hits) / max(1, len(gold.tables)),
        "column_recall": len(column_hits) / len(gold.columns) if gold.columns else None,
        "context_precision": (len(table_hits) + len(column_hits)) / max(1, retrieved_items),
        "schema_recall": (len(table_hits) + len(column_hits)) / max(1, gold_items),
        "foreign_key_recall": (
            len(gold.foreign_keys & selected_joins) / len(gold.foreign_keys)
            if gold.foreign_keys
            else None
        ),
        "join_edge_recall": (
            len(gold.join_edges & selected_joins) / len(gold.join_edges)
            if gold.join_edges
            else None
        ),
        "table_hits": float(len(table_hits)),
        "table_gold": float(len(gold.tables)),
        "column_hits": float(len(column_hits)),
        "column_gold": float(len(gold.columns)),
        "foreign_key_hits": float(len(gold.foreign_keys & selected_joins)),
        "foreign_key_gold": float(len(gold.foreign_keys)),
        "join_edge_hits": float(len(gold.join_edges & selected_joins)),
        "join_edge_gold": float(len(gold.join_edges)),
        "retrieved_items": float(retrieved_items),
    }
