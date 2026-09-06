"""Bounded foreign-key graph operations and minimal join closure."""

from collections import deque
from itertools import combinations
from typing import Literal

from agentic_text2sql.contracts.catalog import CatalogSnapshot

type PathState = tuple[str, list[str], list[str]]
type JoinProvenance = Literal["DECLARED_FK", "INFERRED_UNIQUE_LOOKUP"]


def catalog_join_edges(
    catalog: CatalogSnapshot,
) -> list[tuple[str, str, str, JoinProvenance]]:
    """Return declared FKs plus conservative exact-name unique lookup relationships."""
    edges: list[tuple[str, str, str, JoinProvenance]] = []
    declared_pairs: set[frozenset[str]] = set()
    for table in catalog.tables:
        for foreign_key in table.foreign_keys:
            join = " AND ".join(
                f"{table.name}.{source} = {foreign_key.target_table}.{target}"
                for source, target in zip(
                    foreign_key.from_columns, foreign_key.target_columns, strict=True
                )
            )
            edges.append((table.name, foreign_key.target_table, join, "DECLARED_FK"))
            declared_pairs.add(frozenset({table.name, foreign_key.target_table}))

    raw_tables = [table for table in catalog.tables if table.kind == "table"]
    for left, right in combinations(raw_tables, 2):
        if frozenset({left.name, right.name}) in declared_pairs:
            continue
        left_columns = {column.name: column for column in left.columns}
        right_columns = {column.name: column for column in right.columns}
        for name in sorted(left_columns.keys() & right_columns.keys()):
            left_key = left_columns[name].primary_key_position > 0 or any(
                index.unique and index.columns == (name,) for index in left.indexes
            )
            right_key = right_columns[name].primary_key_position > 0 or any(
                index.unique and index.columns == (name,) for index in right.indexes
            )
            if left_key == right_key:
                continue
            left_type = left_columns[name].data_type.casefold()
            right_type = right_columns[name].data_type.casefold()
            if left_type and right_type and left_type != right_type:
                continue
            edges.append(
                (
                    left.name,
                    right.name,
                    f"{left.name}.{name} = {right.name}.{name}",
                    "INFERRED_UNIQUE_LOOKUP",
                )
            )
    return sorted(set(edges))


def expand_tables(catalog: CatalogSnapshot, seeds: set[str], hops: int = 1) -> set[str]:
    if not 0 <= hops <= 2:
        raise ValueError("FK expansion is bounded to 0..2 hops")
    adjacency: dict[str, set[str]] = {table.name: set() for table in catalog.tables}
    for left, right, _, _ in catalog_join_edges(catalog):
        adjacency[left].add(right)
        adjacency.setdefault(right, set()).add(left)
    selected = set(seeds)
    frontier = set(seeds)
    for _ in range(hops):
        frontier = {
            neighbor for table in frontier for neighbor in adjacency.get(table, ())
        } - selected
        selected.update(frontier)
    return selected


def minimal_join_closure(
    catalog: CatalogSnapshot, ordered_seeds: list[str], max_hops: int = 2
) -> tuple[set[str], list[str]]:
    if not 0 <= max_hops <= 2:
        raise ValueError("join closure is bounded to 0..2 hops")
    adjacency: dict[str, list[tuple[str, str]]] = {table.name: [] for table in catalog.tables}
    for left, right, join, _ in catalog_join_edges(catalog):
        adjacency[left].append((right, join))
        adjacency.setdefault(right, []).append((left, join))
    if not ordered_seeds:
        return set(), []
    selected = {ordered_seeds[0]}
    joins: set[str] = set()
    for target in ordered_seeds[1:]:
        if target in selected:
            continue
        queue: deque[PathState] = deque([(target, [target], [])])
        visited = {target}
        found: tuple[list[str], list[str]] | None = None
        while queue:
            node, path, path_joins = queue.popleft()
            if len(path) - 1 > max_hops:
                continue
            if node in selected:
                found = path, path_joins
                break
            for neighbor, join in sorted(adjacency.get(node, [])):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, [*path, neighbor], [*path_joins, join]))
        if found is None:
            selected.add(target)
        else:
            selected.update(found[0])
            joins.update(found[1])
    return selected, sorted(joins)
