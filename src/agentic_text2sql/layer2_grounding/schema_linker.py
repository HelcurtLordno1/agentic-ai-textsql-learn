"""Plan-aware schema linker with minimal FK closure and a final context budget."""

from __future__ import annotations

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.retrieval import EvidenceItem, RetrievalResult, SchemaContext
from agentic_text2sql.layer2_grounding.context_packer import estimate_tokens, render_schema_context
from agentic_text2sql.layer2_grounding.fk_graph import minimal_join_closure
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


def link_schema(
    plan: LogicalPlan,
    retrieval: RetrievalResult,
    catalog: CatalogSnapshot,
    token_budget: int = 1200,
    max_tables: int = 6,
    fk_hops: int = 2,
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
    table_order: list[str] = []
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
    for seed_count in range(1, len(table_order) + 1):
        tables, joins = minimal_join_closure(catalog, table_order[:seed_count], fk_hops)
        columns = {
            f"{item.document.table}.{item.document.column}"
            for item in ranked
            if item.document.table in tables and item.document.column is not None
        }
        for join in joins:
            for equality in join.split(" AND "):
                left, right = equality.split(" = ", maxsplit=1)
                columns.update((left, right))
        rendered = render_schema_context(catalog, tables, columns, joins)
        tokens = estimate_tokens(rendered)
        if tokens > token_budget:
            break
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
        best = SchemaContext(
            db_id=catalog.db_id,
            selected_tables=sorted(tables),
            selected_columns=sorted(columns),
            joins=joins,
            evidence=evidence,
            catalog_hash=catalog.catalog_hash,
            rendered_context=rendered,
            estimated_tokens=tokens,
        )
    if best is None:
        raise ValueError("even the smallest schema context exceeds the token budget")
    return best
