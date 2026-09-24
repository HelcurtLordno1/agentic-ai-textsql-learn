"""Opt-in, budgeted schema selection that favors owner and role coverage."""

from __future__ import annotations

from itertools import combinations

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.retrieval import (
    EvidenceItem,
    RankedDocument,
    RetrievalResult,
    SchemaContext,
)
from agentic_text2sql.layer2_grounding.context_packer import estimate_tokens, render_schema_context
from agentic_text2sql.layer2_grounding.fk_graph import (
    JoinProvenance,
    catalog_join_edges,
    minimal_join_closure,
)
from agentic_text2sql.layer2_grounding.keyword_index import normalize_tokens

_BOILERPLATE = {"dataset", "olist", "semantic", "table", "view"}


def _words(value: str) -> set[str]:
    """Normalize plural entity names for conservative identifier matching."""
    normalized: set[str] = set()
    for word in normalize_tokens(value):
        if "_" in word:
            continue
        if len(word) > 4 and word.endswith("ies"):
            normalized.add(f"{word[:-3]}y")
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            normalized.add(word[:-1])
        else:
            normalized.add(word)
    return normalized


def _role_groups(plan: LogicalPlan) -> tuple[set[str], ...]:
    values = [
        *plan.metrics,
        *plan.dimensions,
        *plan.filters,
        *plan.sort,
        *plan.required_concepts,
    ]
    return tuple(group for value in values if (group := _words(value)))


def _lexical_owners(catalog: CatalogSnapshot, plan: LogicalPlan, question: str) -> tuple[str, ...]:
    question_words = _words(" ".join((question, *plan.required_concepts)))
    owners: list[str] = []
    for table in catalog.tables:
        identifier = {
            word for word in _words(table.name) if word not in _BOILERPLATE and len(word) > 2
        }
        if identifier and identifier <= question_words:
            owners.append(table.name)
    return tuple(owners)


def _evidence(ranked: list[RankedDocument], tables: set[str]) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            evidence_id=item.document.document_id,
            kind=item.document.kind,
            table=item.document.table,
            column=item.document.column,
            score=item.score,
        )
        for item in ranked
        if item.document.table in tables
    ]


def _candidate_context(
    catalog: CatalogSnapshot,
    ranked: list[RankedDocument],
    tables: set[str],
    joins: list[str],
    provenance: dict[str, JoinProvenance],
    required_columns: set[str],
    terms: set[str],
    token_budget: int,
) -> SchemaContext | None:
    columns = set(required_columns)
    for table in catalog.tables:
        if table.name in tables:
            columns.update(
                f"{table.name}.{column.name}"
                for column in table.columns
                if column.primary_key_position > 0
            )
    for join in joins:
        for equality in join.split(" AND "):
            left, right = equality.split(" = ", maxsplit=1)
            columns.update((left, right))
    rendered = render_schema_context(catalog, tables, columns, joins, provenance)
    if estimate_tokens(rendered) > token_budget:
        return None

    # Keep retrieved columns first, then use remaining budget for plausible columns.
    retrieved = [
        f"{item.document.table}.{item.document.column}"
        for item in ranked
        if item.document.table in tables and item.document.column is not None
    ]
    remaining = [
        f"{table.name}.{column.name}"
        for table in catalog.tables
        if table.name in tables
        for column in table.columns
    ]
    remaining.sort(key=lambda name: (-len(terms & _words(name)), name))
    for column in dict.fromkeys((*retrieved, *remaining)):
        if column in columns:
            continue
        candidate = columns | {column}
        expanded = render_schema_context(catalog, tables, candidate, joins, provenance)
        if estimate_tokens(expanded) <= token_budget:
            columns = candidate
            rendered = expanded
    return SchemaContext(
        db_id=catalog.db_id,
        selected_tables=sorted(tables),
        selected_columns=sorted(columns),
        joins=joins,
        join_provenance=provenance,
        evidence=_evidence(ranked, tables),
        catalog_hash=catalog.catalog_hash,
        rendered_context=rendered,
        estimated_tokens=estimate_tokens(rendered),
    )


def link_schema_with_coverage(
    plan: LogicalPlan,
    retrieval: RetrievalResult,
    catalog: CatalogSnapshot,
    *,
    token_budget: int,
    max_tables: int,
    fk_hops: int,
    preferred_tables: tuple[str, ...],
    required_columns: tuple[str, ...],
    question: str,
) -> SchemaContext:
    if retrieval.db_id != catalog.db_id or retrieval.catalog_hash != catalog.catalog_hash:
        raise ValueError("retrieval result does not belong to the supplied catalog")
    if token_budget < 1 or max_tables < 1 or not 0 <= fk_hops <= 2:
        raise ValueError("invalid bounded schema selection settings")
    known_tables = {table.name for table in catalog.tables}
    known_columns = {
        f"{table.name}.{column.name}" for table in catalog.tables for column in table.columns
    }
    required = set(preferred_tables) | {
        column.split(".", maxsplit=1)[0] for column in required_columns
    }
    if required - known_tables or set(required_columns) - known_columns:
        raise ValueError("required schema owner or column is absent from catalog")
    if len(required) > max_tables:
        raise ValueError("required schema owners exceed the table budget")
    if any(
        item.document.db_id != catalog.db_id
        or item.document.catalog_hash != catalog.catalog_hash
        or item.document.table not in known_tables
        or (
            item.document.column is not None
            and f"{item.document.table}.{item.document.column}" not in known_columns
        )
        for item in retrieval.candidates
    ):
        raise ValueError("retrieval contains stale or foreign catalog evidence")

    terms = _words(
        " ".join(
            (
                question,
                *plan.metrics,
                *plan.dimensions,
                *plan.filters,
                *plan.sort,
                *plan.required_concepts,
            )
        )
    )
    ranked = sorted(
        retrieval.candidates,
        key=lambda item: (
            -len(terms & _words(item.document.retrieval_text())),
            -item.score,
            item.document.document_id,
        ),
    )
    edges = catalog_join_edges(catalog)
    provenance_by_join = {join: source for _, _, join, source in edges}
    all_tables = set(known_tables)
    if len(all_tables) <= max_tables:
        full_columns = set(known_columns)
        full_joins = [join for _, _, join, source in edges if source == "DECLARED_FK"]
        full_provenance = {join: provenance_by_join[join] for join in full_joins}
        full = _candidate_context(
            catalog,
            ranked,
            all_tables,
            full_joins,
            full_provenance,
            full_columns,
            terms,
            token_budget,
        )
        if full is not None:
            return full

    lexical_owners = _lexical_owners(catalog, plan, question)
    table_order = list(dict.fromkeys((*preferred_tables, *sorted(required), *lexical_owners)))
    for item in ranked:
        related = [item.document.table]
        if item.document.kind == "relationship":
            related.extend(
                side.split(".", maxsplit=1)[0]
                for pair in item.document.neighbors
                for side in pair.split("=", maxsplit=1)
            )
        for table in related:
            if table in known_tables and table not in table_order:
                table_order.append(table)
            if len(table_order) >= max_tables:
                break
        if len(table_order) >= max_tables:
            break
    table_order = table_order[:max_tables]
    if not table_order:
        raise ValueError("schema linker received no retrieval candidates or owner evidence")

    best: SchemaContext | None = None
    best_score: tuple[int, int, float, int, int] | None = None
    groups = _role_groups(plan)
    for count in range(1, len(table_order) + 1):
        for seeds in combinations(table_order, count):
            if not required <= set(seeds):
                continue
            tables, joins = minimal_join_closure(catalog, list(seeds), fk_hops)
            if len(tables) > max_tables or not required <= tables:
                continue
            provenance = {join: provenance_by_join[join] for join in joins}
            context = _candidate_context(
                catalog,
                ranked,
                tables,
                joins,
                provenance,
                set(required_columns),
                terms,
                token_budget,
            )
            if context is None:
                continue
            evidence = [item for item in ranked if item.document.table in tables]
            coverage = sum(
                any(group & _words(item.document.retrieval_text()) for item in evidence)
                for group in groups
            )
            support = sum(
                max((item.score for item in evidence if item.document.table == table), default=0)
                for table in tables
            )
            connected = int(len(tables) <= 1 or len(joins) >= len(tables) - 1)
            score = (
                len(set(lexical_owners) & tables),
                coverage,
                support,
                connected,
                -context.estimated_tokens,
            )
            if best_score is None or score > best_score:
                best, best_score = context, score
    if best is None:
        raise ValueError("required owner coverage cannot fit the schema context budget")
    return best
