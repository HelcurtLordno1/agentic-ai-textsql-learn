"""Conservative question/catalog binding for explicit ranking obligations."""

from __future__ import annotations

import re

from sqlglot import exp

from agentic_text2sql.contracts.catalog import CatalogSnapshot


def _words(text: str) -> set[str]:
    # Case/underscore normalization and simple English plurals, not semantic inference.
    tokens = re.findall(r"[^\W_]+", text.casefold())
    return {token[:-1] if token.endswith("s") and len(token) > 3 else token for token in tokens}


def bind_question_metric(question: str, catalog: CatalogSnapshot) -> tuple[str, str] | None:
    question_words = _words(question)
    matches = [
        (table.name, column.name)
        for table in catalog.tables
        for column in table.columns
        if _words(column.name) and _words(column.name).issubset(question_words)
    ]
    # Catalog-wide ambiguity is not resolved by looking at the generated draft.
    return matches[0] if len(matches) == 1 else None


def order_matches_metric(
    statement: exp.Expression,
    question: str,
    catalog: CatalogSnapshot,
) -> bool:
    # Projection aliases belong to SELECT; other query roots need scope-aware binding.
    if not isinstance(statement, exp.Select):
        return False
    bound = bind_question_metric(question, catalog)
    order = statement.args.get("order")
    if bound is None or not isinstance(order, exp.Order) or not order.expressions:
        return False
    column = order.expressions[0].this
    if not isinstance(column, exp.Column):
        return False
    if not column.table:
        projections = [
            item.this
            for item in statement.selects
            if isinstance(item, exp.Alias) and item.alias == column.name
        ]
        if len(projections) > 1:
            return False  # SQLite alias precedence is not independent metric evidence.
        if projections:
            column = projections[0]
            if not isinstance(column, exp.Column):
                return False
    sources = list(statement.find_all(exp.Table))
    aliases = {source.alias_or_name: source.name for source in sources}
    if column.table:
        owner = aliases.get(column.table)
    else:
        owners = [
            source.name
            for source in sources
            if any(
                t.name == source.name and any(c.name == column.name for c in t.columns)
                for t in catalog.tables
            )
        ]
        owner = owners[0] if len(owners) == 1 else None
    return (owner, column.name) == bound
