"""Rule-first conversion from validation signals to an auditable correction plan."""

from __future__ import annotations

from agentic_text2sql.contracts.correction import CorrectionPlan
from agentic_text2sql.contracts.planning import DINSQLPlan, LogicalPlan
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
    "RETURNING_CUSTOMER_REQUIRES_OUTER_COUNT": (
        "Count returning customers at customer grain: prefer customer_order_facts with "
        "order_count > 1, or wrap a customer_unique_id GROUP BY/HAVING subquery in an outer COUNT."
    ),
    "EXPLICIT_CUSTOMER_UNIQUE_ID_MISSING": (
        "The question explicitly names customer_unique_id; count that field from its owning "
        "customer relation and do not substitute customer_id."
    ),
    "EXPLICIT_ORDER_STATUS_MISMATCH": (
        "Preserve the explicitly requested order status using olist_orders_dataset.order_status; "
        "do not substitute another entity, column, or status value."
    ),
    "DELIVERY_POPULATION_NARROWED_BY_STATUS": (
        "Do not filter order_status='delivered'; use non-null delivered timestamps "
        "and the requested date comparison."
    ),
    "PAYMENT_TYPE_RECORD_GRAIN_MISMATCH": (
        "The requested groups are raw payment_type records. Use "
        "olist_order_payments_dataset.payment_type and count rows at payment-record grain; "
        "do not substitute a per-order distinct-payment count."
    ),
    "REVIEW_FREQUENCY_GRAIN_MISMATCH": (
        "Count raw review rows by olist_order_reviews_dataset.review_score; do not substitute "
        "per-order summary maxima or review_row_count."
    ),
    "FREQUENCY_TIE_BREAK_MISSING": (
        "After row count DESC, order the grouped value ASC for deterministic ties."
    ),
    "PRODUCT_CATEGORY_NULL_POPULATION_MISMATCH": (
        "Missing product category means product_category_name IS NULL. Do not broaden the "
        "population with translation-field nulls."
    ),
    "TOP_K_MISSING_ORDER": "Add deterministic ORDER BY matching the ranking intent.",
    "TOP_K_MISSING_LIMIT": "Add the requested LIMIT.",
    "RANKING_ORDER_MISSING": "Order the requested aggregate metric descending.",
    "RANKING_PRIMARY_NOT_DESC": "Use DESC for the primary ranking metric.",
    "RANKING_LIMIT_MISMATCH": "Use the exact top-k LIMIT requested; use LIMIT 1 for 'most'.",
    "ALPHABETICAL_TIE_BREAK_MISSING": (
        "After the descending metric, add the requested name/dimension ASC tie-break."
    ),
    "DISTRIBUTION_LIMIT_UNREQUESTED": (
        "Return the complete grouped distribution; remove LIMIT because the question asks to list "
        "all groups, not only the maximum group."
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

ERROR_CLAUSES: dict[ErrorClass, tuple[str, ...]] = {
    ErrorClass.SYNTAX_ERROR: ("ALL",),
    ErrorClass.UNKNOWN_TABLE: ("FROM", "JOIN"),
    ErrorClass.UNKNOWN_COLUMN: ("SELECT", "WHERE", "GROUP_BY", "HAVING", "ORDER_BY"),
    ErrorClass.AMBIGUOUS_COLUMN: ("SELECT", "JOIN", "WHERE"),
    ErrorClass.TYPE_OR_FUNCTION_ERROR: ("SELECT", "WHERE"),
    ErrorClass.JOIN_ERROR: ("FROM", "JOIN"),
    ErrorClass.FILTER_OR_VALUE_ERROR: ("WHERE", "HAVING"),
    ErrorClass.AGGREGATION_ERROR: ("SELECT", "GROUP_BY", "HAVING"),
    ErrorClass.DIALECT_ERROR: ("ALL",),
    ErrorClass.EMPTY_RESULT_SUSPECTED: ("JOIN", "WHERE"),
    ErrorClass.RESULT_SHAPE_MISMATCH: ("SELECT", "GROUP_BY"),
    ErrorClass.SEMANTIC_MISMATCH: ("SELECT", "WHERE", "GROUP_BY", "ORDER_BY", "LIMIT"),
    ErrorClass.POLICY_VIOLATION: (),
    ErrorClass.TIMEOUT: (),
    ErrorClass.UNKNOWN_RUNTIME_ERROR: (),
}

SIGNAL_CLAUSES: dict[str, tuple[str, ...]] = {
    "SCALAR_AGGREGATE_ROW_COUNT": ("SELECT", "GROUP_BY"),
    "SCALAR_AGGREGATE_COLUMN_COUNT": ("SELECT",),
    "AVERAGE_AGGREGATE_MISSING": ("SELECT",),
    "CUSTOMER_IDENTITY_NOT_UNIQUE": ("FROM", "JOIN", "GROUP_BY"),
    "RETURNING_CUSTOMER_OUTPUT_SHAPE": ("SELECT",),
    "RETURNING_CUSTOMER_REQUIRES_OUTER_COUNT": (
        "SELECT",
        "FROM",
        "JOIN",
        "GROUP_BY",
        "HAVING",
    ),
    "EXPLICIT_CUSTOMER_UNIQUE_ID_MISSING": ("SELECT", "FROM", "JOIN"),
    "EXPLICIT_ORDER_STATUS_MISMATCH": ("FROM", "WHERE"),
    "PAYMENT_TYPE_RECORD_GRAIN_MISMATCH": ("SELECT", "FROM", "GROUP_BY", "ORDER_BY"),
    "REVIEW_FREQUENCY_GRAIN_MISMATCH": ("SELECT", "FROM", "GROUP_BY", "ORDER_BY"),
    "FREQUENCY_TIE_BREAK_MISSING": ("ORDER_BY",),
    "PRODUCT_CATEGORY_NULL_POPULATION_MISMATCH": ("FROM", "WHERE"),
    "DELIVERY_POPULATION_NARROWED_BY_STATUS": ("WHERE",),
    "TOP_K_MISSING_ORDER": ("ORDER_BY",),
    "TOP_K_MISSING_LIMIT": ("LIMIT",),
    "RANKING_ORDER_MISSING": ("ORDER_BY",),
    "RANKING_PRIMARY_NOT_DESC": ("ORDER_BY",),
    "RANKING_LIMIT_MISMATCH": ("LIMIT",),
    "ALPHABETICAL_TIE_BREAK_MISSING": ("ORDER_BY",),
    "DISTRIBUTION_LIMIT_UNREQUESTED": ("LIMIT",),
    "SCALAR_MAXIMUM_AGGREGATE_MISSING": ("SELECT", "GROUP_BY", "ORDER_BY", "LIMIT"),
}


def build_correction_plan(
    report: ValidationReport, plan: LogicalPlan | None = None
) -> CorrectionPlan:
    category = report.error_class or ErrorClass.UNKNOWN_RUNTIME_ERROR
    changes = [ERROR_GUIDANCE[category]]
    changes.extend(SIGNAL_GUIDANCE[item] for item in report.signals if item in SIGNAL_GUIDANCE)
    clauses = [*ERROR_CLAUSES[category]]
    for signal in report.signals:
        clauses.extend(SIGNAL_CLAUSES.get(signal, ()))
    return CorrectionPlan(
        error_class=category,
        suspected_cause=report.safe_message or "Validation rejected the candidate",
        changes_required=tuple(dict.fromkeys(changes)),
        evidence_ids=tuple(report.signals),
        target_clauses=tuple(dict.fromkeys(clauses)),
        clause_expectations=plan.clauses if isinstance(plan, DINSQLPlan) else None,
        should_retry=classify_for_repair(report),
    )
