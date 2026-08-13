"""Rule-first conversion from validation signals to an auditable correction plan."""

from __future__ import annotations

from agentic_text2sql.contracts.correction import CorrectionPlan
from agentic_text2sql.contracts.validation import ErrorClass, ValidationReport
from agentic_text2sql.layer5_correction.classifier import classify_for_repair

ERROR_GUIDANCE: dict[ErrorClass, str] = {
    ErrorClass.SYNTAX_ERROR: "Return one complete syntactically valid SQLite SELECT query.",
    ErrorClass.UNKNOWN_TABLE: "Use only tables present in schema evidence.",
    ErrorClass.UNKNOWN_COLUMN: "Resolve every column against its owning table and alias.",
    ErrorClass.AMBIGUOUS_COLUMN: "Qualify ambiguous columns with the correct table alias.",
    ErrorClass.TYPE_OR_FUNCTION_ERROR: "Use SQLite-compatible functions and argument types.",
    ErrorClass.JOIN_ERROR: "Repair join keys using declared relationships.",
    ErrorClass.FILTER_OR_VALUE_ERROR: "Repair filter values without changing the requested metric.",
    ErrorClass.AGGREGATION_ERROR: "Align aggregation, grouping, and output grain with the plan.",
    ErrorClass.DIALECT_ERROR: "Replace non-SQLite syntax with SQLite syntax.",
    ErrorClass.EMPTY_RESULT_SUSPECTED: "Recheck joins and filters; do not invent unavailable data.",
    ErrorClass.RESULT_SHAPE_MISMATCH: (
        "Return the exact row and column shape requested by the plan."
    ),
    ErrorClass.SEMANTIC_MISMATCH: "Repair only the listed deterministic semantic conflicts.",
    ErrorClass.POLICY_VIOLATION: "Do not retry unsafe SQL.",
    ErrorClass.TIMEOUT: "Do not retry a timed-out query through semantic correction.",
    ErrorClass.UNKNOWN_RUNTIME_ERROR: "Do not retry an unclassified infrastructure failure.",
}

SIGNAL_GUIDANCE = {
    "SCALAR_AGGREGATE_ROW_COUNT": "Produce exactly one result row for the scalar aggregate.",
    "SCALAR_AGGREGATE_COLUMN_COUNT": "Project exactly the requested aggregate metric columns.",
    "AVERAGE_AGGREGATE_MISSING": (
        "Use a real AVG aggregate. For review score, prefer "
        "AVG(olist_order_reviews_dataset.review_score); selecting a per-order "
        "average_review_score column without aggregating it is not an overall scalar average."
    ),
    "CUSTOMER_IDENTITY_NOT_UNIQUE": "Use customer_unique_id as the stable customer identity.",
    "RETURNING_CUSTOMER_OUTPUT_SHAPE": (
        "Project only the single requested returning-customer count."
    ),
    "DELIVERY_POPULATION_NARROWED_BY_STATUS": (
        "Do not filter order_status='delivered'; use non-null delivered timestamps "
        "and the requested date comparison."
    ),
    "TOP_K_MISSING_ORDER": "Add deterministic ORDER BY matching the ranking intent.",
    "TOP_K_MISSING_LIMIT": "Add the requested LIMIT.",
}


def build_correction_plan(report: ValidationReport) -> CorrectionPlan:
    category = report.error_class or ErrorClass.UNKNOWN_RUNTIME_ERROR
    changes = [ERROR_GUIDANCE[category]]
    changes.extend(SIGNAL_GUIDANCE[item] for item in report.signals if item in SIGNAL_GUIDANCE)
    return CorrectionPlan(
        error_class=category,
        suspected_cause=report.safe_message or "Validation rejected the candidate",
        changes_required=tuple(dict.fromkeys(changes)),
        evidence_ids=tuple(report.signals),
        should_retry=classify_for_repair(report),
    )
