"""Deterministic, gold-blind execution-result validation."""

from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.validation import (
    ErrorClass,
    ResultPreview,
    ValidationReport,
    ValidationStatus,
)


def validate_result(result: ResultPreview, plan: LogicalPlan | None = None) -> ValidationReport:
    warnings: list[str] = []
    signals: list[str] = []
    if not result.rows:
        warnings.append("EMPTY_RESULT")
    if result.truncated:
        warnings.append("RESULT_TRUNCATED")
    if plan is not None and plan.task_type == "aggregation" and not plan.dimensions:
        if len(result.rows) != 1:
            signals.append("SCALAR_AGGREGATE_ROW_COUNT")
        expected_columns = max(1, len(plan.metrics))
        if len(result.columns) != expected_columns:
            signals.append("SCALAR_AGGREGATE_COLUMN_COUNT")
    if signals:
        return ValidationReport(
            accepted=False,
            status=ValidationStatus.SUSPICIOUS,
            error_class=ErrorClass.RESULT_SHAPE_MISMATCH,
            safe_message="Query result shape does not match the logical plan",
            warnings=warnings,
            signals=signals,
            repair_eligible=True,
        )
    return ValidationReport(accepted=True, warnings=warnings)
