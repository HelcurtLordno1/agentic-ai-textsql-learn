"""Deterministic execution-result validation."""

from agentic_text2sql.contracts.validation import ResultPreview, ValidationReport


def validate_result(result: ResultPreview) -> ValidationReport:
    warnings: list[str] = []
    if not result.rows:
        warnings.append("EMPTY_RESULT")
    if result.truncated:
        warnings.append("RESULT_TRUNCATED")
    return ValidationReport(accepted=True, warnings=warnings)
