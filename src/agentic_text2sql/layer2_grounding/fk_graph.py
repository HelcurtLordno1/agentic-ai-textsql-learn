"""Bounded foreign-key graph expansion."""

from agentic_text2sql.contracts.catalog import CatalogSnapshot


def expand_tables(catalog: CatalogSnapshot, seeds: set[str], hops: int = 1) -> set[str]:
    if not 0 <= hops <= 2:
        raise ValueError("FK expansion is bounded to 0..2 hops")
    adjacency: dict[str, set[str]] = {table.name: set() for table in catalog.tables}
    for table in catalog.tables:
        for foreign_key in table.foreign_keys:
            adjacency[table.name].add(foreign_key.target_table)
            adjacency.setdefault(foreign_key.target_table, set()).add(table.name)
    selected = set(seeds)
    frontier = set(seeds)
    for _ in range(hops):
        frontier = {
            neighbor for table in frontier for neighbor in adjacency.get(table, ())
        } - selected
        selected.update(frontier)
    return selected
