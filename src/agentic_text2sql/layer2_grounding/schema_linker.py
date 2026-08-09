"""Deterministic schema linker over retrieval evidence."""

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.retrieval import EvidenceItem, RetrievalResult, SchemaContext
from agentic_text2sql.layer2_grounding.fk_graph import expand_tables


def link_schema(
    plan: LogicalPlan, retrieval: RetrievalResult, catalog: CatalogSnapshot, fk_hops: int = 1
) -> SchemaContext:
    del (
        plan
    )  # Typed boundary: deterministic linker currently relies on already-expanded query text.
    if retrieval.db_id != catalog.db_id or retrieval.catalog_hash != catalog.catalog_hash:
        raise ValueError("retrieval result does not belong to the supplied catalog")
    seed_tables = {candidate.document.table for candidate in retrieval.candidates}
    tables = expand_tables(catalog, seed_tables, fk_hops)
    columns = sorted(
        f"{candidate.document.table}.{candidate.document.column}"
        for candidate in retrieval.candidates
        if candidate.document.column is not None
    )
    joins = sorted(
        pair
        for table in catalog.tables
        if table.name in tables
        for fk in table.foreign_keys
        if fk.target_table in tables
        for pair in (
            " AND ".join(
                f"{table.name}.{source} = {fk.target_table}.{target}"
                for source, target in zip(fk.from_columns, fk.target_columns, strict=True)
            ),
        )
    )
    evidence = [
        EvidenceItem(
            evidence_id=item.document.document_id,
            kind=item.document.kind,
            table=item.document.table,
            column=item.document.column,
            score=item.score,
        )
        for item in retrieval.candidates
    ]
    return SchemaContext(
        db_id=catalog.db_id,
        selected_tables=sorted(tables),
        selected_columns=columns,
        joins=joins,
        evidence=evidence,
        catalog_hash=catalog.catalog_hash,
    )
