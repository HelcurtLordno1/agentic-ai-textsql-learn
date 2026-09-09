"""Plan-aware schema linker with minimal FK closure and a final context budget."""

from __future__ import annotations

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.retrieval import EvidenceItem, RetrievalResult, SchemaContext
from agentic_text2sql.layer2_grounding.context_packer import estimate_tokens, render_schema_context
from agentic_text2sql.layer2_grounding.fk_graph import catalog_join_edges, minimal_join_closure
from agentic_text2sql.layer2_grounding.keyword_index import normalize_tokens


def _plan_terms(plan: LogicalPlan) -> set[str]:
    values = [
        *plan.metrics,
        *plan.dimensions,
        *plan.filters,
        *plan.sort,
        *plan.required_concepts,
        *plan.assumptions,
    ]
    return set(normalize_tokens(" ".join(values)))


def _intent_groups(plan: LogicalPlan) -> tuple[set[str], ...]:
    values = [
        *plan.metrics,
        *plan.dimensions,
        *plan.filters,
        *plan.required_concepts,
    ]
    return tuple(tokens for value in values if (tokens := set(normalize_tokens(value))))


def link_schema(
    plan: LogicalPlan,
    retrieval: RetrievalResult,
    catalog: CatalogSnapshot,
    token_budget: int = 1200,
    max_tables: int = 6,
    fk_hops: int = 2,
    preferred_tables: tuple[str, ...] = (),
    required_columns: tuple[str, ...] = (),
) -> SchemaContext:
    if retrieval.db_id != catalog.db_id or retrieval.catalog_hash != catalog.catalog_hash:
        raise ValueError("retrieval result does not belong to the supplied catalog")
    if token_budget < 1 or max_tables < 1:
        raise ValueError("schema budget and max_tables must be positive")
    terms = _plan_terms(plan)
    ranked = sorted(
        retrieval.candidates,
        key=lambda item: (
            -len(terms & set(normalize_tokens(item.document.retrieval_text()))),
            -item.score,
            item.document.document_id,
        ),
    )
    known_tables = {table.name for table in catalog.tables}
    known_columns = {
        f"{table.name}.{column.name}" for table in catalog.tables for column in table.columns
    }
    if unknown := set(preferred_tables) - known_tables:
        raise ValueError(f"preferred tables are absent from catalog: {', '.join(sorted(unknown))}")
    if unknown := set(required_columns) - known_columns:
        raise ValueError(f"required columns are absent from catalog: {', '.join(sorted(unknown))}")
    table_order: list[str] = list(dict.fromkeys(preferred_tables))
    table_order.extend(
        table
        for qualified in required_columns
        if (table := qualified.split(".", maxsplit=1)[0]) not in table_order
    )
    for item in ranked:
        related_tables = [item.document.table]
        if item.document.kind == "relationship":
            related_tables.extend(
                side.split(".", maxsplit=1)[0]
                for pair in item.document.neighbors
                for side in pair.split("=", maxsplit=1)
            )
        for table in related_tables:
            if table not in table_order:
                table_order.append(table)
            if len(table_order) == max_tables:
                break
        if len(table_order) == max_tables:
            break
    if not table_order:
        raise ValueError("schema linker received no retrieval candidates")
    best: SchemaContext | None = None
    best_score: tuple[int, int, int, float, int, int] | None = None
    closures = [minimal_join_closure(catalog, [table], fk_hops) for table in table_order]
    closures.extend(
        minimal_join_closure(catalog, table_order[:seed_count], fk_hops)
        for seed_count in range(2, len(table_order) + 1)
    )
    seen: set[tuple[frozenset[str], tuple[str, ...]]] = set()
    intent_groups = _intent_groups(plan)
    provenance_by_join = {
        join: provenance for _, _, join, provenance in catalog_join_edges(catalog)
    }
    for tables, joins in closures:
        closure_key = (frozenset(tables), tuple(joins))
        if closure_key in seen:
            continue
        seen.add(closure_key)
        columns = {
            f"{item.document.table}.{item.document.column}"
            for item in ranked
            if item.document.table in tables and item.document.column is not None
        }
        columns.update(
            column for column in required_columns if column.split(".", maxsplit=1)[0] in tables
        )
        for join in joins:
            for equality in join.split(" AND "):
                left, right = equality.split(" = ", maxsplit=1)
                columns.update((left, right))
        join_provenance = {join: provenance_by_join[join] for join in joins}
        rendered = render_schema_context(catalog, tables, columns, joins, join_provenance)
        tokens = estimate_tokens(rendered)
        if tokens > token_budget:
            continue
        evidence = [
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
        context = SchemaContext(
            db_id=catalog.db_id,
            selected_tables=sorted(tables),
            selected_columns=sorted(columns),
            joins=joins,
            join_provenance=join_provenance,
            evidence=evidence,
            catalog_hash=catalog.catalog_hash,
            rendered_context=rendered,
            estimated_tokens=tokens,
        )
        evidence_tokens = [
            set(normalize_tokens(item.document.retrieval_text()))
            for item in ranked
            if item.document.table in tables
        ]
        coverage = sum(
            any(group & document_tokens for document_tokens in evidence_tokens)
            for group in intent_groups
        )
        connected = int(len(tables) <= 1 or len(joins) >= len(tables) - 1)
        evidence_quality = sum(item.score for item in evidence) / max(1, len(evidence))
        preferred_coverage = sum(table in tables for table in preferred_tables)
        score = (
            preferred_coverage,
            coverage,
            connected,
            evidence_quality,
            -len(tables),
            -tokens,
        )
        if best_score is None or score > best_score:
            best = context
            best_score = score
    if best is None:
        raise ValueError("even the smallest schema context exceeds the token budget")
    return best
