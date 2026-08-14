"""Public Layer 4 service composing policy, execution, and validation."""

from __future__ import annotations

from pathlib import Path

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.validation import ResultPreview, ValidationReport
from agentic_text2sql.layer4_validation.error_normalizer import normalize_error
from agentic_text2sql.layer4_validation.executor import ReadOnlySQLiteExecutor
from agentic_text2sql.layer4_validation.policy import SQLSafetyPolicy
from agentic_text2sql.layer4_validation.result_validator import validate_result
from agentic_text2sql.layer4_validation.semantic_checks import validate_semantics


class ValidationService:
    def __init__(
        self,
        policy: SQLSafetyPolicy | None = None,
        executor: ReadOnlySQLiteExecutor | None = None,
    ) -> None:
        self.policy = policy or SQLSafetyPolicy()
        self.executor = executor or ReadOnlySQLiteExecutor()

    def run(
        self,
        database: Path,
        sql: str,
        catalog: CatalogSnapshot,
        *,
        question: str | None = None,
        plan: LogicalPlan | None = None,
    ) -> tuple[ValidationReport, ResultPreview | None]:
        decision = self.policy.evaluate(sql, catalog)
        if not decision.allowed or decision.normalized_sql is None:
            return (
                ValidationReport(
                    accepted=False,
                    error_class=decision.error_class,
                    safe_message=decision.safe_message,
                ),
                None,
            )
        try:
            result = self.executor.execute(database, decision.normalized_sql)
        except Exception as exc:  # Stable error boundary for database adapters.
            return normalize_error(exc), None
        result_report = validate_result(result, plan)
        if not result_report.accepted:
            if question is not None and plan is not None:
                semantic_report = validate_semantics(
                    question, plan, decision.normalized_sql, db_id=catalog.db_id
                )
                result_report.signals.extend(
                    signal
                    for signal in semantic_report.signals
                    if signal not in result_report.signals
                )
            return result_report, result
        if question is not None and plan is not None:
            semantic_report = validate_semantics(
                question, plan, decision.normalized_sql, db_id=catalog.db_id
            )
            semantic_report.warnings.extend(result_report.warnings)
            return semantic_report, result
        return result_report, result
