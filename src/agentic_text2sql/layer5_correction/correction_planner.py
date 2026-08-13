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
    "RANKING_ORDER_MISSING": "Order the requested aggregate metric descending.",
    "RANKING_PRIMARY_NOT_DESC": "Use DESC for the primary ranking metric.",
    "RANKING_LIMIT_MISMATCH": "Use the exact top-k LIMIT requested; use LIMIT 1 for 'most'.",
    "ALPHABETICAL_TIE_BREAK_MISSING": (
        "After the descending metric, add the requested name/dimension ASC tie-break."
    ),
    "SCALAR_MAXIMUM_AGGREGATE_MISSING": "Return one scalar MAX(...) value, not the winning row.",
    "RECORD_COUNT_MUST_NOT_BE_DISTINCT": (
        "The question explicitly counts records/rows; use COUNT(*) rather than DISTINCT identity."
    ),
    "FREIGHT_PER_ORDER_GRAIN_MISMATCH": (
        "Average freight at order grain using order_item_totals.freight_cents."
    ),
    "MULTIPLE_REVIEW_ROWS_RULE_MISSING": (
        "Count orders from order_review_summary where review_row_count > 1."
    ),
    "PRODUCT_PHOTO_QUANTITY_FILTER_MISSING": (
        "Count products where olist_products_dataset.product_photos_qty > 1."
    ),
    "YEAR_MONTH_CONTEXT_LOST": (
        "Preserve year-month (YYYY-MM) when grouping timestamps; do not collapse all years by %m."
    ),
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
