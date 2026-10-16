"""CPU clause checks with explicit scope and catalog-backed fan-out risks."""

from __future__ import annotations

import re
from typing import Literal

from sqlglot import exp

from agentic_text2sql.contracts.assessment import (
    CheckOutcome,
    ClauseAssessment,
    ClauseFinding,
)
from agentic_text2sql.contracts.catalog import CatalogSnapshot, TableInfo
from agentic_text2sql.layer4_validation.parser import parse_one
from agentic_text2sql.layer4_validation.rank_binding import order_matches_metric

# Narrow explicit instructions only. Natural language outside this scope stays UNKNOWN.
TOP = re.compile(
    r"\b(top|bottom)\s+([1-9]\d{0,2})\b|\b([1-9]\d{0,2})\s+\w+\s+(cao|thấp) nhất\b", re.I
)


def _unique_key(table: TableInfo, columns: tuple[str, ...]) -> bool:
    primary = tuple(
        c.name
        for c in sorted(table.columns, key=lambda c: c.primary_key_position)
        if c.primary_key_position
    )
    # Catalog index records do not expose partial/expression scope. Only PK metadata
    # establishes unconditional uniqueness here; a possible fan-out remains a risk.
    return bool(primary and set(primary).issubset(columns))


def assess_clauses(question: str, sql: str, catalog: CatalogSnapshot) -> ClauseAssessment:
    statement = parse_one(sql)
    findings: list[ClauseFinding] = []
    simple = isinstance(statement, exp.Select) and not any(
        statement.find(kind) is not None for kind in (exp.Subquery, exp.CTE, exp.Window)
    )
    rank_simple = simple and not (
        statement.find(exp.AggFunc) is not None and statement.args.get("group") is None
    )  # Scalar aggregate can implement top-1 through MIN/MAX.
    rank = TOP.search(question)
    # Negations, ties and scalar maximums need an independent intent interpretation.
    ambiguous = re.search(
        r"\b(not|without|except|ties|tied|maximum|minimum|không|trừ|hòa|hoà)\b", question, re.I
    )
    directions = re.findall(r"\b(highest|largest|most|lowest|smallest|least)\b", question, re.I)
    polarities = {word.casefold() in {"highest", "largest", "most"} for word in directions}
    if rank and rank_simple and not ambiguous and len(polarities) <= 1:
        span = rank.group(0)
        count = int(rank.group(2) or rank.group(3))
        # 'top' without a metric direction is ambiguous (e.g. top 3 youngest).
        descending = rank.group(1) and rank.group(1).casefold() == "top"
        direction = re.search(r"\b(highest|largest|most|lowest|smallest|least)\b", question, re.I)
        if direction:
            descending = direction.group(0).casefold() in {"highest", "largest", "most"}
        if rank.group(4):
            descending = rank.group(4).casefold() == "cao"
        order = statement.args.get("order")
        if not isinstance(order, exp.Order):
            findings.append(
                ClauseFinding(
                    code="EXPLICIT_RANK_ORDER_MISSING",
                    clause="ORDER BY",
                    outcome=CheckOutcome.CONTRADICTION,
                    message="Explicit ranked rows require an outer ORDER BY",
                    evidence_ids=("question",),
                    question_span=span,
                )
            )
        elif (
            order.expressions
            and (direction or rank.group(4))
            and isinstance(order.expressions[0].this, exp.Column)
            and order_matches_metric(statement, question, catalog)
        ):
            wrong = bool(order.expressions[0].args.get("desc")) != bool(descending)
            findings.append(
                ClauseFinding(
                    code="EXPLICIT_RANK_DIRECTION",
                    clause="ORDER BY",
                    outcome=CheckOutcome.CONTRADICTION if wrong else CheckOutcome.SUPPORTED,
                    message="Compare primary order direction with explicit highest/lowest wording",
                    evidence_ids=("question",),
                    question_span=direction.group(0) if direction else span,
                )
            )
        elif order.expressions and (direction or rank.group(4)):
            findings.append(
                ClauseFinding(
                    code="RANK_METRIC_BINDING_UNKNOWN",
                    clause="ORDER BY",
                    outcome=CheckOutcome.UNKNOWN,
                    message="Ordering expression is not independently bound to the question metric",
                    evidence_ids=("question",),
                    question_span=span,
                )
            )
        limit = statement.args.get("limit")
        value = limit.expression if isinstance(limit, exp.Limit) else None
        actual = int(value.this) if isinstance(value, exp.Literal) and value.is_int else None
        offset = statement.args.get("offset")
        if offset is not None:
            findings.append(
                ClauseFinding(
                    code="RANK_OFFSET_UNKNOWN",
                    clause="LIMIT",
                    outcome=CheckOutcome.UNKNOWN,
                    message="Offset changes the ranked population; requires intent review",
                    evidence_ids=("question",),
                    question_span=span,
                )
            )
        else:
            findings.append(
                ClauseFinding(
                    code="EXPLICIT_RANK_LIMIT",
                    clause="LIMIT",
                    outcome=CheckOutcome.SUPPORTED
                    if actual == count
                    else CheckOutcome.CONTRADICTION,
                    message=f"Explicit request asks for {count} ranked rows",
                    evidence_ids=("question",),
                    question_span=span,
                )
            )
    else:
        findings.append(
            ClauseFinding(
                code="RANK_INTENT_UNKNOWN",
                clause="ORDER BY",
                outcome=CheckOutcome.UNKNOWN,
                message="No independent, in-scope explicit ranking obligation",
            )
        )

    # Inspect direct sources only. Never flatten CTE/EXISTS scopes into one join grain.
    if simple:
        sources = list(statement.find_all(exp.Table))
        tables = {table.name: table for table in catalog.tables}
        for parent_source in sources:
            parent = tables.get(parent_source.name)
            if parent is None:
                continue
            children: list[str] = []
            for source in sources:
                child = tables.get(source.name)
                if child is None or source is parent_source:
                    continue
                for fk in child.foreign_keys:
                    if fk.target_table == parent.name and not _unique_key(child, fk.from_columns):
                        children.append(child.name)
                        break
            if len(children) >= 2 and statement.find(exp.AggFunc) is not None:
                findings.append(
                    ClauseFinding(
                        code="SIBLING_JOIN_GRAIN_UNKNOWN",
                        clause="JOIN",
                        outcome=CheckOutcome.UNKNOWN,
                        message="Nonunique child sources may multiply aggregates; inspect grain",
                        evidence_ids=tuple(f"catalog:{name}" for name in sorted(set(children))),
                    )
                )
                break
    findings.append(
        ClauseFinding(
            code="SEMANTIC_COVERAGE_UNKNOWN",
            clause="QUERY",
            outcome=CheckOutcome.UNKNOWN,
            message="Population, binding, values and general semantic equivalence are not proven",
        )
    )
    obligations: tuple[tuple[Literal["SELECT", "WHERE", "GROUP BY"], str, str], ...] = (
        ("SELECT", "OUTPUT_BINDING_UNKNOWN", "Output ownership needs independent intent binding"),
        (
            "WHERE",
            "POPULATION_PREDICATE_UNKNOWN",
            "Population and values are not proven by execution",
        ),
        ("GROUP BY", "ENTITY_GRAIN_UNKNOWN", "Entity grain and aggregate lineage need evidence"),
    )
    for clause, code, message in obligations:
        findings.append(
            ClauseFinding(code=code, clause=clause, outcome=CheckOutcome.UNKNOWN, message=message)
        )
    return ClauseAssessment(
        findings=tuple(findings),
        semantic_status="CONTRADICTION"
        if any(f.outcome is CheckOutcome.CONTRADICTION for f in findings)
        else "UNVERIFIED",
    )
