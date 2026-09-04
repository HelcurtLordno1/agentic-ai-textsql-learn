"""Plan-aware schema linker with minimal FK closure and a final context budget."""

from __future__ import annotations

import re

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.retrieval import EvidenceItem, RetrievalResult, SchemaContext
from agentic_text2sql.layer2_grounding.context_packer import estimate_tokens, render_schema_context
from agentic_text2sql.layer2_grounding.fk_graph import minimal_join_closure
from agentic_text2sql.layer2_grounding.keyword_index import normalize_tokens

_TABLE_BOILERPLATE = frozenset({"dataset", "fact", "facts", "olist", "table", "view"})
_AGGREGATE_PREFIX = re.compile(
    r"^(?:average|avg|mean|total|sum|minimum|min|maximum|max|count|number\s+of)\s+"
)


def _identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _exact_metric_owner_tables(plan: LogicalPlan, catalog: CatalogSnapshot) -> set[str]:
    """Find raw columns that exactly implement a scalar aggregate measure."""
    if plan.dimensions or plan.filters or plan.task_type != "aggregation":
        return set()
    measures = {
        _identifier(_AGGREGATE_PREFIX.sub("", metric.casefold()))
        for metric in plan.metrics
        if _AGGREGATE_PREFIX.match(metric.casefold())
    } - {""}
    return {
        table.name
        for table in catalog.tables
        if any(column.name.casefold() in measures for column in table.columns)
    }


def _exact_dimension_matches(plan: LogicalPlan, catalog: CatalogSnapshot) -> dict[str, int]:
    dimensions = {_identifier(value) for value in plan.dimensions} - {""}
    return {
        table.name: sum(column.name.casefold() in dimensions for column in table.columns)
        for table in catalog.tables
    }


def _entity_owner_tables(plan: LogicalPlan, catalog: CatalogSnapshot) -> list[str]:
    """Prefer the base entity relation for unqualified entity-count metrics."""
    metric_tokens = set(normalize_tokens(" ".join([*plan.metrics, *plan.required_concepts])))
    if "count" not in metric_tokens and not metric_tokens & {"number", "quantity", "so", "luong"}:
        return []
    qualifiers = {
        "average",
        "avg",
        "delivery",
        "item",
        "items",
        "maximum",
        "minimum",
        "payment",
        "payments",
        "repeat",
        "repeated",
        "returning",
        "review",
        "revenue",
    }
    if plan.dimensions or plan.filters or metric_tokens & qualifiers:
        return []
    entities = metric_tokens & {
        "order",
        "orders",
        "customer",
        "customers",
        "product",
        "products",
        "seller",
        "sellers",
    }
    singular_entities = {value.removesuffix("s") for value in entities}
    owners: list[str] = []
    for table in catalog.tables:
        core = {
            token
            for token in normalize_tokens(table.name)
            if "_" not in token and token not in _TABLE_BOILERPLATE
        }
        singular_core = {value.removesuffix("s") for value in core}
        if len(singular_core) == 1 and singular_core & singular_entities:
            owners.append(table.name)
    return sorted(owners)


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


def _intent_terms(plan: LogicalPlan) -> tuple[set[str], set[str], set[str], set[str]]:
    dimensions = set(normalize_tokens(" ".join(plan.dimensions)))
    metrics = set(normalize_tokens(" ".join(plan.metrics)))
    filters = set(normalize_tokens(" ".join(plan.filters)))
    intent = set(
        normalize_tokens(
            " ".join([*plan.metrics, *plan.dimensions, *plan.filters, *plan.required_concepts])
        )
    )
    return dimensions, metrics, filters, intent


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
    dimension_terms, metric_terms, filter_terms, intent_terms = _intent_terms(plan)
    ranked = sorted(
        retrieval.candidates,
        key=lambda item: (
            -item.score,
            -len(terms & set(normalize_tokens(item.document.retrieval_text()))),
            item.document.document_id,
        ),
    )
    owner_tables = set(_entity_owner_tables(plan, catalog)) | _exact_metric_owner_tables(
        plan, catalog
    )
    exact_dimension_matches = _exact_dimension_matches(plan, catalog)
    dimension_owner_tables = {
        table for table, count in exact_dimension_matches.items() if count > 0
    }
    table_order: list[str] = sorted(owner_tables | dimension_owner_tables)
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
    best_score: tuple[int, int, int, int, int, int, float, int, int] | None = None
    closure_candidates: list[tuple[set[str], list[str]]] = [
        minimal_join_closure(catalog, [seed], fk_hops) for seed in table_order
    ]
    closure_candidates.extend(
        minimal_join_closure(catalog, table_order[:seed_count], fk_hops)
        for seed_count in range(2, len(table_order) + 1)
    )
    seen_closures: set[tuple[frozenset[str], tuple[str, ...]]] = set()
    for tables, joins in closure_candidates:
        closure_key = (frozenset(tables), tuple(joins))
        if closure_key in seen_closures:
            continue
        seen_closures.add(closure_key)
        columns = {
            f"{item.document.table}.{item.document.column}"
            for item in ranked
            if item.document.table in tables and item.document.column is not None
        }
        informative_terms = intent_terms - {
            "id",
            "order",
            "orders",
            "customer",
            "customers",
            "product",
            "products",
            "table",
            "dataset",
        }
        for catalog_table in catalog.tables:
            if catalog_table.name not in tables:
                continue
            for column in catalog_table.columns:
                if informative_terms & set(normalize_tokens(column.name)):
                    columns.add(f"{catalog_table.name}.{column.name}")
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
        context = SchemaContext(
            db_id=catalog.db_id,
            selected_tables=sorted(tables),
            selected_columns=sorted(columns),
            joins=joins,
            evidence=evidence,
            catalog_hash=catalog.catalog_hash,
            rendered_context=rendered,
            estimated_tokens=tokens,
        )
        schema_terms = set(normalize_tokens(rendered))
        evidence_quality = sum(item.score for item in evidence) / max(1, len(evidence))
        score = (
            int(bool(owner_tables & tables)),
            sum(exact_dimension_matches.get(table, 0) for table in tables),
            len(dimension_terms & schema_terms),
            len(filter_terms & schema_terms),
            len(metric_terms & schema_terms),
            len(intent_terms & schema_terms),
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
