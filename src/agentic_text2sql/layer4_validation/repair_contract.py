"""Compile a small, evidence-bounded AST edit before spending repair compute."""

from __future__ import annotations

import re
from typing import Literal

from sqlglot import exp

from agentic_text2sql.contracts.assessment import ClauseAssessment, RepairContract
from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.validation import ValidationReport
from agentic_text2sql.layer4_validation.clause_critic import TOP
from agentic_text2sql.layer4_validation.parser import parse_one
from agentic_text2sql.layer4_validation.rank_binding import (
    bind_question_metric,
    order_matches_metric,
)

RANK_CODES = frozenset(
    {
        "EXPLICIT_RANK_ORDER_MISSING",
        "EXPLICIT_RANK_DIRECTION",
        "EXPLICIT_RANK_LIMIT",
    }
)


def compile_repair_contract(
    question: str,
    sql: str,
    catalog: CatalogSnapshot,
    checks: ClauseAssessment,
) -> RepairContract:
    def unknown(reason: str) -> RepairContract:
        return RepairContract(eligible=False, reason=reason)

    codes = checks.contradictions
    if not codes or not codes.issubset(RANK_CODES):
        return unknown("No supported deterministic edit obligation")
    statement = parse_one(sql)
    if (
        not isinstance(statement, exp.Select)
        or any(
            statement.find(kind) is not None
            for kind in (exp.Subquery, exp.CTE, exp.Window, exp.AggFunc, exp.Join)
        )
        or any(
            statement.args.get(key) is not None for key in ("group", "having", "offset", "distinct")
        )
    ):
        return unknown("Ranking edit requires one simple source without aggregate/scope ambiguity")
    sources = list(statement.find_all(exp.Table))
    if len(sources) != 1:
        return unknown("Ranking edit requires exactly one source")
    bound = bind_question_metric(question, catalog)
    if bound is None or bound[0] != sources[0].name:
        return unknown("Question/catalog metric binding is absent or ambiguous")
    rank = TOP.search(question)
    direction = re.search(r"\b(highest|largest|most|lowest|smallest|least)\b", question, re.I)
    if rank is None or not (direction or rank.group(4)):
        return unknown("Explicit count and metric direction are required")
    count = int(rank.group(2) or rank.group(3))
    if count > 200:
        return unknown("Requested count exceeds bounded complete preview")
    descending = (
        direction.group(0).casefold() in {"highest", "largest", "most"}
        if direction
        else rank.group(4).casefold() == "cao"
    )
    repaired = statement.copy()
    allowed: list[Literal["order", "limit"]] = []
    if statement.args.get("order") is None:
        column = exp.column(bound[1], table=sources[0].alias_or_name, quoted=True)
        repaired = repaired.order_by(
            exp.Ordered(this=column, desc=descending, nulls_first=not descending)
        )
        allowed.append("order")
    elif not order_matches_metric(statement, question, catalog):
        return unknown("Existing order key does not bind to the independent question metric")
    elif "EXPLICIT_RANK_DIRECTION" in codes:
        order = repaired.args["order"]
        order.expressions[0].set("desc", descending)
        order.expressions[0].set("nulls_first", not descending)
        allowed.append("order")
    if "EXPLICIT_RANK_LIMIT" in codes:
        repaired = repaired.limit(count)
        allowed.append("limit")
    if not allowed:
        return unknown("No admissible AST field to change")
    return RepairContract(
        eligible=True,
        reason="Explicit ranking goal bound independently to one catalog metric",
        evidence_ids=("question", f"catalog:{bound[0]}"),
        question_spans=(rank.group(0), direction.group(0) if direction else rank.group(0)),
        target_codes=tuple(sorted(codes)),
        allowed_fields=tuple(allowed),
        metric=f"{bound[0]}.{bound[1]}",
        planned_sql=repaired.sql(dialect="sqlite"),
    )


def admit_contract_repair(
    contract: RepairContract,
    sql: str,
    validation: ValidationReport,
    before: ClauseAssessment,
    after: ClauseAssessment,
) -> bool:
    if not contract.eligible or contract.planned_sql is None or not validation.accepted:
        return False
    old_unknown = {
        finding.code for finding in before.findings if finding.outcome.value == "UNKNOWN"
    }
    new_unknown = {finding.code for finding in after.findings if finding.outcome.value == "UNKNOWN"}
    return bool(
        parse_one(sql) == parse_one(contract.planned_sql)
        and after.contradictions < before.contradictions
        and new_unknown.issubset(old_unknown)
    )
