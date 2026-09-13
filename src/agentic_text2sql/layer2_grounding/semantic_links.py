"""Deterministic, provenance-preserving schema links for DIN-SQL planning."""

from __future__ import annotations

import re

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import (
    DecomposedQuestion,
    SemanticLink,
    SemanticLinkPlan,
    SemanticRole,
)
from agentic_text2sql.contracts.retrieval import RankedDocument, RetrievalResult, SchemaContext
from agentic_text2sql.contracts.semantics import BindingStatus, SemanticBinding
from agentic_text2sql.layer2_grounding.keyword_index import normalize_tokens

_QUOTED_VALUE = re.compile(r"['\"]([^'\"]{1,120})['\"]")
_TABLE_BOILERPLATE = {"dataset", "olist", "semantic", "table", "view"}


def _tokens(value: str) -> set[str]:
    return {token for token in normalize_tokens(value) if len(token) > 1}


def _best_document(
    mention: str,
    candidates: tuple[RankedDocument, ...],
    selected_tables: set[str],
    *,
    table_only: bool = False,
    role: SemanticRole | None = None,
    value: str | None = None,
) -> RankedDocument | None:
    mention_tokens = _tokens(mention)
    ranked: list[tuple[int, int, int, float, str, RankedDocument]] = []
    for candidate in candidates:
        document = candidate.document
        if document.table not in selected_tables or document.kind == "relationship":
            continue
        if table_only and document.kind != "table":
            continue
        overlap = len(mention_tokens & _tokens(document.retrieval_text()))
        if overlap == 0:
            continue
        status_match = int(
            role is SemanticRole.FILTER
            and document.column is not None
            and document.column.casefold().endswith("status")
        )
        ranked.append(
            (
                status_match,
                overlap,
                int(document.kind == "column"),
                candidate.score,
                document.document_id,
                candidate,
            )
        )
    if not ranked:
        return None
    return max(ranked, key=lambda item: (item[0], item[1], item[2], item[3], item[4]))[5]


def _is_unambiguous(
    mention: str,
    candidates: tuple[RankedDocument, ...],
    selected_tables: set[str],
    *,
    table_only: bool,
) -> bool:
    mention_tokens = _tokens(mention)
    matches = {
        (candidate.document.table, candidate.document.column)
        for candidate in candidates
        if candidate.document.table in selected_tables
        and candidate.document.kind != "relationship"
        and (not table_only or candidate.document.kind == "table")
        and mention_tokens & _tokens(candidate.document.retrieval_text())
    }
    return len(matches) == 1


def build_semantic_link_plan(
    question: str,
    decomposition: DecomposedQuestion,
    retrieval: RetrievalResult,
    context: SchemaContext,
    catalog: CatalogSnapshot,
    binding: SemanticBinding | None = None,
) -> SemanticLinkPlan:
    """Map intent mentions to retrieved catalog evidence without reading database values."""
    if retrieval.db_id != context.db_id or retrieval.catalog_hash != context.catalog_hash:
        raise ValueError("retrieval and schema context identities do not match")
    if catalog.db_id != context.db_id or catalog.catalog_hash != context.catalog_hash:
        raise ValueError("catalog and schema context identities do not match")
    selected = set(context.selected_tables)
    mentions: list[tuple[SemanticRole, str, str | None]] = [
        *((SemanticRole.ENTITY, value, None) for value in decomposition.entity_hints),
        *((SemanticRole.METRIC, value, None) for value in decomposition.metric_hints),
        *((SemanticRole.DIMENSION, value, None) for value in decomposition.dimension_hints),
        *((SemanticRole.FILTER, value, value) for value in decomposition.filter_hints),
        *((SemanticRole.VALUE, value, value) for value in decomposition.time_hints),
        *((SemanticRole.VALUE, value, value) for value in _QUOTED_VALUE.findall(question)),
    ]
    links: list[SemanticLink] = []
    unmatched: list[str] = []
    for role, mention, value in mentions:
        status_evidence = next(
            (
                evidence
                for evidence in context.evidence
                if role is SemanticRole.FILTER
                and evidence.column is not None
                and evidence.column.casefold().endswith("status")
            ),
            None,
        )
        if status_evidence is None and role is SemanticRole.FILTER:
            status_columns = [
                qualified
                for qualified in context.selected_columns
                if qualified.rsplit(".", maxsplit=1)[-1].casefold().endswith("status")
            ]
            if len(status_columns) == 1:
                status_table, status_column = status_columns[0].split(".", maxsplit=1)
                links.append(
                    SemanticLink(
                        mention=mention,
                        role=role,
                        table=status_table,
                        column=status_column,
                        value=value,
                        evidence_id=f"{context.db_id}.{status_table}.{status_column}",
                        score=0,
                        required=True,
                    )
                )
                continue
        if status_evidence is not None:
            links.append(
                SemanticLink(
                    mention=mention,
                    role=role,
                    table=status_evidence.table,
                    column=status_evidence.column,
                    value=value,
                    evidence_id=status_evidence.evidence_id,
                    score=status_evidence.score,
                    required=True,
                )
            )
            continue
        candidate = _best_document(
            mention,
            retrieval.candidates,
            selected,
            table_only=role is SemanticRole.ENTITY,
            role=role,
            value=value,
        )
        if candidate is None:
            unmatched.append(mention)
            continue
        document = candidate.document
        links.append(
            SemanticLink(
                mention=mention,
                role=role,
                table=document.table,
                column=document.column,
                value=value,
                evidence_id=document.document_id,
                score=candidate.score,
                required=_is_unambiguous(
                    mention,
                    retrieval.candidates,
                    selected,
                    table_only=role is SemanticRole.ENTITY,
                ),
            )
        )

    question_tokens = _tokens(question)
    table_candidates = [
        candidate
        for candidate in retrieval.candidates
        if candidate.document.kind == "table"
        and candidate.document.table in selected
        and question_tokens & _tokens(candidate.document.retrieval_text())
    ]
    if table_candidates and not any(link.role is SemanticRole.ENTITY for link in links):
        candidate = max(
            table_candidates,
            key=lambda item: (
                len(question_tokens & _tokens(item.document.retrieval_text())),
                item.score,
                item.document.document_id,
            ),
        )
        document = candidate.document
        links.append(
            SemanticLink(
                mention=document.table,
                role=SemanticRole.ENTITY,
                table=document.table,
                evidence_id=document.document_id,
                score=candidate.score,
            )
        )

    unique_links = {
        (link.role, link.mention, link.table, link.column, link.value): link for link in links
    }
    ordered_links = tuple(
        sorted(
            unique_links.values(),
            key=lambda item: (item.role, item.mention, item.table, item.column or ""),
        )
    )
    asks_population = any(
        phrase in question.casefold()
        for phrase in ("how many", "có bao nhiêu", "count ", "number of", "số lượng")
    )
    population_candidates: list[str] = []
    if asks_population and len(decomposition.entity_hints) == 1:
        entity_tokens = _tokens(decomposition.entity_hints[0])
        for table in catalog.tables:
            if table.kind != "table" or table.name not in selected:
                continue
            table_tokens = {
                token
                for token in normalize_tokens(table.name)
                if "_" not in token and token not in _TABLE_BOILERPLATE
            }
            if table_tokens == entity_tokens:
                population_candidates.append(table.name)
    population_owner = population_candidates[0] if len(population_candidates) == 1 else None
    scalar_metric = bool(
        decomposition.metric_hints
        and not decomposition.dimension_hints
        and not decomposition.filter_hints
    )
    required_tables = (
        binding.required_tables
        if binding is not None and binding.status is BindingStatus.PROVEN
        else tuple(
            sorted(
                {
                    link.table
                    for link in ordered_links
                    if link.required and not (scalar_metric and link.role is SemanticRole.ENTITY)
                }
                | ({population_owner} if population_owner is not None else set())
            )
        )
    )
    if binding is not None and binding.status is BindingStatus.PROVEN:
        if binding.aggregate is not None:
            population_owner = binding.aggregate.table
        elif binding.frequency_ranking is not None:
            population_owner = binding.frequency_ranking.table
        else:  # Defensive boundary for externally constructed payloads.
            raise ValueError("proven semantic binding has no typed proof")
    return SemanticLinkPlan(
        db_id=context.db_id,
        catalog_hash=context.catalog_hash,
        links=ordered_links,
        population_owner=population_owner,
        required_tables=required_tables,
        join_paths=tuple(context.joins),
        unmatched_mentions=tuple(dict.fromkeys(unmatched)),
        binding=binding,
    )
