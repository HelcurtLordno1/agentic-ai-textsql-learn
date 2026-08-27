"""Gold-aware, offline failure intelligence for frozen Spider releases.

This module belongs to ``agentic_text2sql_eval`` deliberately. Runtime code must never import it.
Persisted analysis contains structural signatures, hashes, and result shapes—not gold SQL or rows.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlglot import exp, parse_one
from sqlglot.errors import ParseError

from agentic_text2sql.adapters.sqlite_text import decode_sqlite_text
from agentic_text2sql_eval.spider_release import LoadedSpiderCase, _execute


class FailureCause(StrEnum):
    RUNTIME_OR_POLICY = "runtime_or_policy"
    SQL_PARSE = "sql_parse"
    JOIN_OR_SOURCE = "join_or_source"
    NESTING_OR_SET = "nesting_or_set"
    FILTER_OR_VALUE = "filter_or_value"
    AGGREGATION_OR_GRAIN = "aggregation_or_grain"
    PROJECTION = "projection"
    RANKING_OR_LIMIT = "ranking_or_limit"
    UNRESOLVED_SEMANTIC = "unresolved_semantic"


class SqlStructure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    tables: tuple[str, ...]
    columns: tuple[str, ...]
    aggregate_functions: tuple[str, ...]
    predicate_fingerprints: tuple[str, ...]
    literal_fingerprints: tuple[str, ...]
    join_count: int = Field(ge=0)
    group_expression_count: int = Field(ge=0)
    has_having: bool
    has_distinct: bool
    has_order: bool
    has_limit: bool
    nested_select_count: int = Field(ge=0)
    set_operation_count: int = Field(ge=0)
    output_arity: int = Field(ge=0)


class ResultShape(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class FailureEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    db_id: str
    complexity: str
    partition: str
    final_category: str
    primary_cause: FailureCause
    candidate_causes: tuple[FailureCause, ...]
    signals: tuple[str, ...]
    predicted_structure: SqlStructure | None
    gold_structure: SqlStructure | None
    predicted_shape: ResultShape | None
    gold_shape: ResultShape | None
    review_required: bool = True


class FailureAnalysisReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = 1
    analysis_id: str
    source_evaluation_id: str
    source_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_git_commit: str
    case_count: int = Field(ge=1)
    correct_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    by_primary_cause: dict[str, int]
    cases: tuple[FailureEvidence, ...]
    limitations: tuple[str, ...]


class ReviewerLabel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reviewer_id: str = Field(min_length=1, max_length=80)
    case_id: str
    primary_cause: FailureCause


class ReviewAgreement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reviewer_a: str
    reviewer_b: str
    case_count: int = Field(ge=1)
    agreed_count: int = Field(ge=0)
    exact_agreement: float = Field(ge=0, le=1)
    cohens_kappa: float = Field(ge=-1, le=1)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical(expression: exp.Expression) -> str:
    return expression.sql(dialect="sqlite", normalize=True, pretty=False)


def inspect_sql(sql: str) -> SqlStructure:
    statement = parse_one(sql, read="sqlite")
    selects = list(statement.find_all(exp.Select))
    top_select = statement if isinstance(statement, exp.Select) else statement.find(exp.Select)
    groups = list(statement.find_all(exp.Group))
    aggregate_names = sorted(
        type(node).__name__.casefold() for node in statement.find_all(exp.AggFunc)
    )
    predicate_nodes: list[exp.Expression] = [
        *statement.find_all(exp.Where),
        *statement.find_all(exp.Having),
    ]
    literal_hashes = sorted(
        _sha256_text(_canonical(node)) for node in statement.find_all(exp.Literal)
    )
    set_operations = sum(
        1 for node in statement.walk() if isinstance(node, exp.Union | exp.Except | exp.Intersect)
    )
    output_arity = len(top_select.expressions) if top_select is not None else 0
    return SqlStructure(
        fingerprint=_sha256_text(_canonical(statement)),
        tables=tuple(sorted({table.name.casefold() for table in statement.find_all(exp.Table)})),
        columns=tuple(
            sorted({column.name.casefold() for column in statement.find_all(exp.Column)})
        ),
        aggregate_functions=tuple(aggregate_names),
        predicate_fingerprints=tuple(
            sorted(_sha256_text(_canonical(node)) for node in predicate_nodes)
        ),
        literal_fingerprints=tuple(literal_hashes),
        join_count=sum(1 for _ in statement.find_all(exp.Join)),
        group_expression_count=sum(len(group.expressions) for group in groups),
        has_having=statement.find(exp.Having) is not None,
        has_distinct=any(select.args.get("distinct") is not None for select in selects),
        has_order=statement.find(exp.Order) is not None,
        has_limit=statement.find(exp.Limit) is not None,
        nested_select_count=max(0, len(selects) - 1),
        set_operation_count=set_operations,
        output_arity=output_arity,
    )


def _result_shape(rows: list[list[Any]]) -> ResultShape:
    return ResultShape(
        row_count=len(rows),
        column_count=len(rows[0]) if rows else 0,
        result_hash=_sha256_text(repr(rows)),
    )


def _structural_signals(predicted: SqlStructure, gold: SqlStructure) -> tuple[str, ...]:
    signals: list[str] = []
    comparisons = {
        "table_set_differs": predicted.tables != gold.tables,
        "column_set_differs": predicted.columns != gold.columns,
        "join_count_differs": predicted.join_count != gold.join_count,
        "nested_select_count_differs": predicted.nested_select_count != gold.nested_select_count,
        "set_operation_count_differs": predicted.set_operation_count != gold.set_operation_count,
        "predicate_structure_differs": predicted.predicate_fingerprints
        != gold.predicate_fingerprints,
        "literal_set_differs": predicted.literal_fingerprints != gold.literal_fingerprints,
        "aggregate_functions_differ": predicted.aggregate_functions != gold.aggregate_functions,
        "group_expression_count_differs": (
            predicted.group_expression_count != gold.group_expression_count
        ),
        "having_presence_differs": predicted.has_having != gold.has_having,
        "distinct_presence_differs": predicted.has_distinct != gold.has_distinct,
        "output_arity_differs": predicted.output_arity != gold.output_arity,
        "order_presence_differs": predicted.has_order != gold.has_order,
        "limit_presence_differs": predicted.has_limit != gold.has_limit,
    }
    signals.extend(name for name, differs in comparisons.items() if differs)
    return tuple(signals)


def _candidate_causes(signals: tuple[str, ...]) -> tuple[FailureCause, ...]:
    signal_set = set(signals)
    candidates: list[FailureCause] = []
    cause_signals = (
        (FailureCause.JOIN_OR_SOURCE, {"table_set_differs", "join_count_differs"}),
        (
            FailureCause.NESTING_OR_SET,
            {"nested_select_count_differs", "set_operation_count_differs"},
        ),
        (
            FailureCause.FILTER_OR_VALUE,
            {"predicate_structure_differs", "literal_set_differs"},
        ),
        (
            FailureCause.AGGREGATION_OR_GRAIN,
            {
                "aggregate_functions_differ",
                "group_expression_count_differs",
                "having_presence_differs",
                "distinct_presence_differs",
            },
        ),
        (FailureCause.PROJECTION, {"column_set_differs", "output_arity_differs"}),
        (FailureCause.RANKING_OR_LIMIT, {"order_presence_differs", "limit_presence_differs"}),
    )
    for cause, relevant in cause_signals:
        if signal_set & relevant:
            candidates.append(cause)
    return tuple(candidates or [FailureCause.UNRESOLVED_SEMANTIC])


def _source_commit(report: dict[str, Any]) -> str:
    provenance = report.get("provenance")
    if not isinstance(provenance, dict):
        return "unknown"
    commit = provenance.get("git_commit")
    return str(commit) if commit else "unknown"


def analyze_spider_failures(
    *,
    spider_root: Path,
    cases: list[LoadedSpiderCase],
    release_report: dict[str, Any],
    source_report_sha256: str,
    analysis_id: str,
    timeout_seconds: float = 10.0,
) -> FailureAnalysisReport:
    """Analyze a completed report after inference has stopped and gold is allowed."""
    if release_report.get("release_status") != "complete":
        raise ValueError("failure analysis requires a complete release report")
    details = release_report.get("details")
    if not isinstance(details, list):
        raise ValueError("release report has no case details")
    by_id = {str(item["id"]): item for item in details if isinstance(item, dict) and "id" in item}
    expected_ids = {case.id for case in cases}
    if set(by_id) != expected_ids or len(by_id) != len(cases):
        raise ValueError("release report details do not match the frozen case manifest")

    evidence: list[FailureEvidence] = []
    connections: dict[str, sqlite3.Connection] = {}
    try:
        for case in cases:
            detail = by_id[case.id]
            if bool(detail.get("result_correct")):
                continue
            final_category = str(
                detail.get("failure_category") or detail.get("status") or "UNKNOWN"
            )
            generated_sql = detail.get("generated_sql")
            predicted_structure: SqlStructure | None = None
            gold_structure: SqlStructure | None = None
            predicted_shape: ResultShape | None = None
            gold_shape: ResultShape | None = None
            signals: tuple[str, ...] = ()
            candidates: tuple[FailureCause, ...]
            if final_category != "EXECUTION_MISMATCH" or not isinstance(generated_sql, str):
                candidates = (FailureCause.RUNTIME_OR_POLICY,)
            else:
                try:
                    predicted_structure = inspect_sql(generated_sql)
                    gold_structure = inspect_sql(case.gold_sql)
                    signals = _structural_signals(predicted_structure, gold_structure)
                    candidates = _candidate_causes(signals)
                    connection = connections.get(case.db_id)
                    if connection is None:
                        database = spider_root / "database" / case.db_id / f"{case.db_id}.sqlite"
                        connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
                        connection.text_factory = decode_sqlite_text
                        connection.execute("PRAGMA query_only=ON")
                        connections[case.db_id] = connection
                    predicted_shape = _result_shape(
                        _execute(connection, generated_sql, timeout_seconds)
                    )
                    gold_shape = _result_shape(_execute(connection, case.gold_sql, timeout_seconds))
                    if predicted_shape.row_count != gold_shape.row_count:
                        signals = (*signals, "row_count_differs")
                    if predicted_shape.column_count != gold_shape.column_count:
                        signals = (*signals, "result_width_differs")
                except (ParseError, sqlite3.Error, ValueError):
                    candidates = (FailureCause.SQL_PARSE,)
                    signals = (*signals, "analysis_parse_or_execution_failed")
            evidence.append(
                FailureEvidence(
                    case_id=case.id,
                    db_id=case.db_id,
                    complexity=case.complexity,
                    partition=case.partition,
                    final_category=final_category,
                    primary_cause=candidates[0],
                    candidate_causes=candidates,
                    signals=signals,
                    predicted_structure=predicted_structure,
                    gold_structure=gold_structure,
                    predicted_shape=predicted_shape,
                    gold_shape=gold_shape,
                )
            )
    finally:
        for connection in connections.values():
            connection.close()

    counts = Counter(item.primary_cause.value for item in evidence)
    correct_count = len(cases) - len(evidence)
    return FailureAnalysisReport(
        analysis_id=analysis_id,
        source_evaluation_id=str(release_report.get("evaluation_id", "unknown")),
        source_report_sha256=source_report_sha256,
        source_git_commit=_source_commit(release_report),
        case_count=len(cases),
        correct_count=correct_count,
        failure_count=len(evidence),
        review_required_count=sum(item.review_required for item in evidence),
        by_primary_cause=dict(counts.most_common()),
        cases=tuple(evidence),
        limitations=(
            "Primary causes are deterministic hypotheses from structural deltas, not human labels.",
            "Equivalent SQL may have different structures; every failure remains review-required.",
            "Gold SQL and result rows are intentionally absent from the persisted analysis.",
        ),
    )


def load_reviewer_labels(path: Path) -> list[ReviewerLabel]:
    labels = [
        ReviewerLabel.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not labels or len({label.case_id for label in labels}) != len(labels):
        raise ValueError("review label file must contain unique, non-empty case IDs")
    if len({label.reviewer_id for label in labels}) != 1:
        raise ValueError("one review label file must belong to exactly one reviewer")
    return labels


def calculate_review_agreement(
    labels_a: list[ReviewerLabel], labels_b: list[ReviewerLabel]
) -> ReviewAgreement:
    by_a = {label.case_id: label for label in labels_a}
    by_b = {label.case_id: label for label in labels_b}
    if set(by_a) != set(by_b) or not by_a:
        raise ValueError("reviewers must label the same non-empty case set")
    reviewer_a = next(iter(by_a.values())).reviewer_id
    reviewer_b = next(iter(by_b.values())).reviewer_id
    if reviewer_a == reviewer_b:
        raise ValueError("agreement requires two distinct reviewers")
    agreed = sum(by_a[case_id].primary_cause == by_b[case_id].primary_cause for case_id in by_a)
    total = len(by_a)
    proportions_a = Counter(label.primary_cause for label in by_a.values())
    proportions_b = Counter(label.primary_cause for label in by_b.values())
    expected = sum(
        proportions_a[cause] / total * proportions_b[cause] / total for cause in FailureCause
    )
    observed = agreed / total
    kappa = 1.0 if expected == 1.0 and observed == 1.0 else (observed - expected) / (1 - expected)
    return ReviewAgreement(
        reviewer_a=reviewer_a,
        reviewer_b=reviewer_b,
        case_count=total,
        agreed_count=agreed,
        exact_agreement=observed,
        cohens_kappa=kappa,
    )


def write_analysis(report: FailureAnalysisReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload
