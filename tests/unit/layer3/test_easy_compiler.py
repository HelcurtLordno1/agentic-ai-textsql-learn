from pathlib import Path

from agentic_text2sql.contracts.planning import (
    ClausePlan,
    ComplexityDecision,
    ComplexityKind,
    DINSQLPlan,
    PlanningStrategy,
    SemanticLinkPlan,
)
from agentic_text2sql.contracts.semantics import (
    AggregateOperator,
    AggregateSpec,
    BindingStatus,
    ComparisonOperator,
    PredicateSpec,
    SemanticBinding,
)
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer3_generation.easy_compiler import GroundedEasyCompiler
from agentic_text2sql.layer3_generation.normalizer import CandidateNormalizer

ROOT = Path(__file__).resolve().parents[3]
DATABASE = ROOT / "data/processed/olist.sqlite"


def _plan(
    aggregate: AggregateSpec,
    predicates: tuple[PredicateSpec, ...] = (),
) -> DINSQLPlan:
    catalog = SQLiteIntrospector().inspect(DATABASE, "olist")
    required_columns = tuple(
        dict.fromkeys(
            [
                *(
                    [f"{aggregate.table}.{aggregate.column}"]
                    if aggregate.column is not None
                    else []
                ),
                *(f"{predicate.table}.{predicate.column}" for predicate in predicates),
            ]
        )
    )
    binding = SemanticBinding(
        db_id="olist",
        catalog_hash=catalog.catalog_hash,
        status=BindingStatus.PROVEN,
        aggregate=aggregate,
        predicates=predicates,
        required_tables=(aggregate.table,),
        required_columns=required_columns,
        rule_ids=("test.fixture",),
    )
    return DINSQLPlan(
        question_language="en",
        task_type="aggregation",
        metrics=["fixture"],
        semantic_links=SemanticLinkPlan(
            db_id="olist",
            catalog_hash=catalog.catalog_hash,
            required_tables=(aggregate.table,),
            binding=binding,
        ),
        complexity=ComplexityDecision(
            kind=ComplexityKind.AGGREGATE,
            strategy=PlanningStrategy.EASY,
            signals=("proven_semantic_binding",),
        ),
        clauses=ClausePlan(
            select=["human-readable text is not executable input"],
            from_tables=[aggregate.table],
            where=["human-readable predicate"] if predicates else [],
            output_grain="one scalar row",
            aggregate=aggregate,
            predicates=list(predicates),
        ),
    )


def _compile(plan: DINSQLPlan) -> str | None:
    catalog = SQLiteIntrospector().inspect(DATABASE, "olist")
    candidate = GroundedEasyCompiler(CandidateNormalizer()).compile(plan, catalog)
    return candidate.normalized_sql if candidate is not None else None


def test_compiles_typed_count_with_canonical_status_predicate() -> None:
    aggregate = AggregateSpec(
        operator=AggregateOperator.COUNT_ROWS,
        table="olist_orders_dataset",
        evidence_id="semantic.entity.orders",
    )
    predicate = PredicateSpec(
        table="olist_orders_dataset",
        column="order_status",
        operator=ComparisonOperator.EQ,
        value="delivered",
        evidence_id="semantic.filter.order_status",
    )
    sql = _compile(_plan(aggregate, (predicate,)))
    assert sql == "SELECT COUNT(*) FROM olist_orders_dataset WHERE order_status = 'delivered'"


def test_compiles_typed_sum_and_distinct_count() -> None:
    summed = AggregateSpec(
        operator=AggregateOperator.SUM,
        table="order_item_totals",
        column="product_revenue_cents",
        evidence_id="semantic.metric.product_revenue",
    )
    distinct = AggregateSpec(
        operator=AggregateOperator.COUNT_DISTINCT,
        table="olist_customers_dataset",
        column="customer_unique_id",
        evidence_id="semantic.entity.customers",
    )
    assert _compile(_plan(summed)) == "SELECT SUM(product_revenue_cents) FROM order_item_totals"
    assert (
        _compile(_plan(distinct))
        == "SELECT COUNT(DISTINCT customer_unique_id) FROM olist_customers_dataset"
    )


def test_compiles_typed_numeric_comparison_for_derived_semantics() -> None:
    aggregate = AggregateSpec(
        operator=AggregateOperator.COUNT_ROWS,
        table="customer_order_facts",
        evidence_id="semantic.derived.repeat_customer",
    )
    predicate = PredicateSpec(
        table="customer_order_facts",
        column="order_count",
        operator=ComparisonOperator.GT,
        value=1,
        evidence_id="semantic.derived.repeat_customer.order_count",
    )
    assert (
        _compile(_plan(aggregate, (predicate,)))
        == "SELECT COUNT(*) FROM customer_order_facts WHERE order_count > 1"
    )


def test_refuses_unknown_identifier_tampered_contract_and_non_scalar_shape() -> None:
    unknown = _plan(
        AggregateSpec(
            operator=AggregateOperator.SUM,
            table="order_item_totals",
            column="invented_revenue",
            evidence_id="test.unknown",
        )
    )
    assert _compile(unknown) is None

    valid = _plan(
        AggregateSpec(
            operator=AggregateOperator.SUM,
            table="order_item_totals",
            column="product_revenue_cents",
            evidence_id="semantic.metric.product_revenue",
        )
    )
    tampered = valid.model_copy(
        update={"clauses": valid.clauses.model_copy(update={"aggregate": None})}
    )
    assert _compile(tampered) is None
    grouped = valid.model_copy(
        update={"clauses": valid.clauses.model_copy(update={"group_by": ["category"]})}
    )
    assert _compile(grouped) is None
