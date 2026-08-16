"""Bounded foreign-key graph operations and minimal join closure."""

from collections import deque

from agentic_text2sql.contracts.catalog import CatalogSnapshot

type PathState = tuple[str, list[str], list[str]]


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


def minimal_join_closure(
    catalog: CatalogSnapshot, ordered_seeds: list[str], max_hops: int = 2
) -> tuple[set[str], list[str]]:
    if not 0 <= max_hops <= 2:
        raise ValueError("join closure is bounded to 0..2 hops")
    adjacency: dict[str, list[tuple[str, str]]] = {table.name: [] for table in catalog.tables}
    for table in catalog.tables:
        for foreign_key in table.foreign_keys:
            join = " AND ".join(
                f"{table.name}.{source} = {foreign_key.target_table}.{target}"
                for source, target in zip(
                    foreign_key.from_columns, foreign_key.target_columns, strict=True
                )
            )
            adjacency[table.name].append((foreign_key.target_table, join))
            adjacency.setdefault(foreign_key.target_table, []).append((table.name, join))
    seeds = list(dict.fromkeys(seed for seed in ordered_seeds if seed in adjacency))
    if not seeds:
        return set(), []

    def closure_from(anchor: str) -> tuple[set[str], set[str]]:
        selected = {anchor}
        joins: set[str] = set()
        for target in seeds:
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
            if found is not None:
                selected.update(found[0])
                joins.update(found[1])
        return selected, joins

    seed_set = set(seeds)
    candidates = [closure_from(anchor) for anchor in seeds]
    # Prefer the component covering the most retrieved evidence, then the smallest
    # closure. Stable iteration preserves retrieval rank for an exact tie.
    selected, joins = max(
        candidates,
        key=lambda candidate: (
            len(candidate[0] & seed_set),
            -len(candidate[0]),
        ),
    )
    return selected, sorted(joins)
