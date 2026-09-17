from agentic_text2sql.contracts.semantics import (
    AggregateOperator,
    AggregateSpec,
    BindingStatus,
    ComparisonOperator,
    FrequencyRankingSpec,
    PredicateSpec,
    SemanticBinding,
)
from agentic_text2sql.layer4_validation.binding_validator import validate_sql_against_binding


def test_frequency_binding_detects_owner_and_clause_contradictions_cross_domain() -> None:
    binding = SemanticBinding(
        db_id="music",
        catalog_hash="catalog1",
        status=BindingStatus.PROVEN,
        frequency_ranking=FrequencyRankingSpec(
            table="plays",
            dimension_column="genre",
            evidence_id="schema.plays.genre",
            source_grain="one row per play event",
            limit=1,
        ),
        required_tables=("plays",),
        required_columns=("plays.genre",),
    )
    correct = (
        "SELECT genre, COUNT(*) AS n FROM plays GROUP BY genre ORDER BY n DESC, genre ASC LIMIT 1"
    )
    wrong = "SELECT genre, COUNT(*) AS n FROM albums GROUP BY genre ORDER BY genre ASC LIMIT 5"

    assert validate_sql_against_binding(correct, binding) == ()
    assert set(validate_sql_against_binding(wrong, binding)) == {
        "TYPED_OWNER_MISSING",
        "FREQUENCY_COUNT_DESC_MISSING",
        "FREQUENCY_DIMENSION_TIE_BREAK_MISSING",
        "TYPED_LIMIT_MISMATCH",
    }


def test_aggregate_binding_checks_operator_rounding_and_predicate() -> None:
    aggregate = AggregateSpec(
        operator=AggregateOperator.AVG,
        table="shipment_facts",
        column="fee_cents",
        evidence_id="semantic.shipping_fee",
        source_grain="one row per shipment_id",
        rounding_digits=2,
    )
    predicate = PredicateSpec(
        table="shipment_facts",
        column="delivered",
        operator=ComparisonOperator.EQ,
        value=1,
        evidence_id="semantic.delivered",
    )
    binding = SemanticBinding(
        db_id="shipping",
        catalog_hash="catalog1",
        status=BindingStatus.PROVEN,
        aggregate=aggregate,
        predicates=(predicate,),
        required_tables=("shipment_facts",),
        required_columns=("shipment_facts.fee_cents", "shipment_facts.delivered"),
    )

    assert (
        validate_sql_against_binding(
            "SELECT ROUND(AVG(fee_cents), 2) FROM shipment_facts WHERE delivered = 1",
            binding,
        )
        == ()
    )
    assert set(
        validate_sql_against_binding(
            "SELECT SUM(fee_cents) FROM shipment_facts",
            binding,
        )
    ) == {
        "TYPED_AGGREGATE_MISMATCH",
        "TYPED_ROUNDING_MISMATCH",
        "TYPED_PREDICATE_MISSING:delivered",
    }


def test_null_predicate_is_checked_as_ast_semantics() -> None:
    aggregate = AggregateSpec(
        operator=AggregateOperator.COUNT_ROWS,
        table="products",
        evidence_id="semantic.products",
    )
    predicate = PredicateSpec(
        table="products",
        column="category",
        operator=ComparisonOperator.IS_NULL,
        value=None,
        evidence_id="semantic.products.missing_category",
    )
    binding = SemanticBinding(
        db_id="shop",
        catalog_hash="catalog1",
        status=BindingStatus.PROVEN,
        aggregate=aggregate,
        predicates=(predicate,),
        required_tables=("products",),
        required_columns=("products.category",),
    )

    assert (
        validate_sql_against_binding(
            "SELECT COUNT(*) FROM products WHERE category IS NULL", binding
        )
        == ()
    )
    assert validate_sql_against_binding(
        "SELECT COUNT(*) FROM products WHERE category = 'unknown'", binding
    ) == ("TYPED_PREDICATE_MISSING:category",)


def test_weighted_average_proof_rejects_unweighted_rewrite() -> None:
    binding = SemanticBinding(
        db_id="reviews",
        catalog_hash="catalog1",
        status=BindingStatus.PROVEN,
        aggregate=AggregateSpec(
            operator=AggregateOperator.AVG,
            table="review_summary",
            column="average_score",
            weight_column="review_count",
            evidence_id="semantic.average_review",
        ),
        required_tables=("review_summary",),
        required_columns=("review_summary.average_score", "review_summary.review_count"),
    )
    weighted = (
        "SELECT SUM(average_score * review_count) / NULLIF(SUM(review_count), 0) "
        "FROM review_summary"
    )
    unweighted = "SELECT AVG(average_score) FROM review_summary"

    assert validate_sql_against_binding(weighted, binding) == ()
    assert validate_sql_against_binding(unweighted, binding) == ("TYPED_WEIGHTED_AVERAGE_MISMATCH",)
