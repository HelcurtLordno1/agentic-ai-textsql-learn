from __future__ import annotations

from pathlib import Path

import pytest

from agentic_text2sql.contracts.retrieval import (
    CatalogDocument,
    RankedDocument,
    RetrievalResult,
)
from agentic_text2sql.layer1_reasoning.decomposer import Decomposer
from agentic_text2sql.layer1_reasoning.plan_validator import validate_plan
from agentic_text2sql.layer1_reasoning.planner import PlannerAgent
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer2_grounding.semantic_catalog import load_semantic_catalog
from agentic_text2sql.layer2_grounding.service import GroundingService
from agentic_text2sql.layer3_generation.easy_compiler import GroundedEasyCompiler
from agentic_text2sql.layer3_generation.normalizer import CandidateNormalizer
from agentic_text2sql.layer4_validation.executor import ReadOnlySQLiteExecutor

ROOT = Path(__file__).resolve().parents[2]
DATABASE = ROOT / "data/processed/olist.sqlite"


class UnusedProvider:
    def generate_structured(self, **_: object) -> None:
        raise AssertionError("a proven semantic plan must not call the generation model")


class FixedRetriever:
    def __init__(self, catalog_hash: str) -> None:
        document = CatalogDocument(
            document_id="olist.olist_orders_dataset",
            db_id="olist",
            kind="table",
            table="olist_orders_dataset",
            description="orders table",
            catalog_hash=catalog_hash,
        )
        self.result = RetrievalResult(
            db_id="olist",
            mode="hybrid",
            candidates=(RankedDocument(document=document, score=1, sources=("bm25",)),),
            estimated_tokens=10,
            catalog_hash=catalog_hash,
        )

    def retrieve(self, *_: object, **__: object) -> RetrievalResult:
        return self.result


@pytest.mark.parametrize(
    ("question", "expected_sql", "execute"),
    [
        (
            "Count all marketplace sellers",
            "SELECT COUNT(*) FROM olist_sellers_dataset",
            True,
        ),
        (
            "What is total merchandise revenue?",
            "SELECT SUM(product_revenue_cents) FROM order_item_totals",
            False,
        ),
        (
            "Đếm đơn hàng đã hủy",
            "SELECT COUNT(*) FROM olist_orders_dataset WHERE order_status = 'canceled'",
            True,
        ),
        (
            "How many repeat customers do we have?",
            "SELECT COUNT(*) FROM customer_order_facts WHERE order_count > 1",
            False,
        ),
        (
            "How many orders with multiple payment methods?",
            "SELECT COUNT(*) FROM order_payment_totals WHERE distinct_payment_type_count > 1",
            False,
        ),
        (
            "What is the average item count per order?",
            "SELECT AVG(item_count) FROM order_item_totals",
            False,
        ),
        (
            "Trung bình mỗi đơn có bao nhiêu item, làm tròn 4 chữ số?",
            "SELECT ROUND(AVG(item_count), 4) FROM order_item_totals",
            False,
        ),
        (
            "Số đơn hàng lớn nhất từng được ghi nhận cho một customer_unique_id là bao nhiêu?",
            "SELECT MAX(order_count) FROM customer_order_facts",
            False,
        ),
        (
            "Điểm review nào xuất hiện nhiều nhất? Trả về điểm và số review.",
            "SELECT review_score, COUNT(*) AS frequency_count "
            "FROM olist_order_reviews_dataset GROUP BY review_score "
            "ORDER BY frequency_count DESC, review_score LIMIT 1",
            False,
        ),
        (
            "Which payment type has the most payment records? Return type and count.",
            "SELECT payment_type, COUNT(*) AS frequency_count "
            "FROM olist_order_payments_dataset GROUP BY payment_type "
            "ORDER BY frequency_count DESC, payment_type LIMIT 1",
            False,
        ),
        (
            "What is the average freight amount per order in cents rounded to 2 decimals?",
            "SELECT ROUND(AVG(freight_cents), 2) FROM order_item_totals",
            False,
        ),
    ],
)
def test_semantic_construction_runs_end_to_end_without_a_model_call(
    question: str,
    expected_sql: str,
    execute: bool,
) -> None:
    catalog = SQLiteIntrospector().inspect(DATABASE, "olist")
    semantics = load_semantic_catalog(ROOT / "datasets/olist/semantic_catalog.yaml", catalog)
    grounding = GroundingService(  # type: ignore[arg-type]
        FixedRetriever(catalog.catalog_hash),
        catalog,
        mode="hybrid",
        semantic_catalog=semantics,
    )
    decomposition = Decomposer().decompose(question)
    context, links = grounding.prepare_for_planning(question, decomposition)
    planner = PlannerAgent(  # type: ignore[arg-type]
        UnusedProvider(),
        ROOT / "configs/prompts/planner_v2.j2",
    )
    plan = planner.plan_grounded(question, decomposition, links, context)
    validation = validate_plan(plan, catalog, context)
    assert validation.accepted
    assert validation.signals == ()

    candidate = GroundedEasyCompiler(CandidateNormalizer()).compile(plan, catalog)
    assert candidate is not None
    assert candidate.normalized_sql == expected_sql
    if execute:
        result = ReadOnlySQLiteExecutor().execute(DATABASE, candidate.normalized_sql)
        assert len(result.rows) == 1
        assert len(result.rows[0]) == 1
        assert result.rows[0][0] is not None
