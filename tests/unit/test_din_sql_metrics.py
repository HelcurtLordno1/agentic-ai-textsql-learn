from pathlib import Path

from agentic_text2sql.contracts.planning import (
    ClausePlan,
    ComplexityDecision,
    ComplexityKind,
    DINSQLPlan,
    JoinStep,
    PlanningStrategy,
    SemanticLinkPlan,
)
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql_eval.din_sql_metrics import evaluate_plan

ROOT = Path(__file__).resolve().parents[2]


def test_clause_metrics_measure_plan_and_generated_sql_separately() -> None:
    catalog = SQLiteIntrospector().inspect(
        ROOT / "data/samples/synthetic_commerce_tiny.sqlite", "synthetic"
    )
    plan = DINSQLPlan(
        question_language="en",
        task_type="ranking",
        metrics=["item count"],
        dimensions=["category"],
        limit=2,
        semantic_links=SemanticLinkPlan(db_id="synthetic", catalog_hash=catalog.catalog_hash),
        complexity=ComplexityDecision(
            kind=ComplexityKind.MULTI_JOIN,
            strategy=PlanningStrategy.NON_NESTED,
        ),
        clauses=ClausePlan(
            select=["products.category", "COUNT(order_items.product_id)"],
            from_tables=["products", "order_items"],
            joins=[
                JoinStep(
                    left_table="products",
                    right_table="order_items",
                    condition="products.product_id = order_items.product_id",
                    purpose="attach category",
                )
            ],
            group_by=["products.category"],
            order_by=["item count descending"],
            limit=2,
            output_grain="one row per category",
        ),
    )
    sql = (
        "SELECT p.category, COUNT(*) FROM products p JOIN order_items i "
        "ON p.product_id = i.product_id GROUP BY p.category ORDER BY COUNT(*) DESC LIMIT 2"
    )
    metrics = evaluate_plan(
        plan.model_dump(mode="json"), gold_sql=sql, predicted_sql=sql, catalog=catalog
    )
    assert metrics["clause_exact"]
    assert metrics["clause_f1"]["f1"] == 1
    assert metrics["schema"]["table_recall"] == 1
    assert metrics["schema"]["join_recall"] == 1
    assert metrics["plan_to_sql"]["clause_agreement"] == 1
