"""Conservative static warnings for joins that can multiply business grains."""

from __future__ import annotations

from sqlglot import exp

from agentic_text2sql.layer4_validation.parser import parse_one

MANY_GRAIN_TABLES = {
    "olist_order_items_dataset",
    "olist_order_payments_dataset",
    "olist_order_reviews_dataset",
}


def join_grain_signals(sql: str) -> list[str]:
    statement = parse_one(sql)
    tables = {table.name for table in statement.find_all(exp.Table)}
    risky = sorted(tables & MANY_GRAIN_TABLES)
    if len(risky) < 2:
        return []
    if statement.find(exp.Distinct) is not None:
        return []
    return ["POTENTIAL_MULTI_GRAIN_FANOUT:" + ",".join(risky)]
