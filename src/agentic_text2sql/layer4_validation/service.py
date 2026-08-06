"""Public Layer 4 service composing policy, execution, and validation."""

from __future__ import annotations

from pathlib import Path

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.validation import ResultPreview, ValidationReport
from agentic_text2sql.layer4_validation.error_normalizer import normalize_error
from agentic_text2sql.layer4_validation.executor import ReadOnlySQLiteExecutor
from agentic_text2sql.layer4_validation.policy import SQLSafetyPolicy
from agentic_text2sql.layer4_validation.result_validator import validate_result


class ValidationService:
    def __init__(
        self,
        policy: SQLSafetyPolicy | None = None,
        executor: ReadOnlySQLiteExecutor | None = None,
    ) -> None:
        self.policy = policy or SQLSafetyPolicy()
        self.executor = executor or ReadOnlySQLiteExecutor()

    def run(
        self, database: Path, sql: str, catalog: CatalogSnapshot
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
        return validate_result(result), result
