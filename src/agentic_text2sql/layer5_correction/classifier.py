"""Deterministic repair eligibility classifier."""

from agentic_text2sql.contracts.validation import ErrorClass, ValidationReport

NON_REPAIRABLE = {
    ErrorClass.POLICY_VIOLATION,
    ErrorClass.TIMEOUT,
    ErrorClass.UNKNOWN_RUNTIME_ERROR,
}


def classify_for_repair(report: ValidationReport) -> bool:
    return (
        not report.accepted
        and report.error_class is not None
        and report.error_class not in NON_REPAIRABLE
        and (report.repair_eligible or report.error_class is not ErrorClass.POLICY_VIOLATION)
    )
