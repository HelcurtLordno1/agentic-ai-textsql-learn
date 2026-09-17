from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from agentic_text2sql.contracts.planning import SemanticLinkPlan
from agentic_text2sql.contracts.retrieval import SchemaContext
from agentic_text2sql.contracts.semantics import BindingStatus
from agentic_text2sql.layer1_reasoning.decomposer import Decomposer
from agentic_text2sql.layer1_reasoning.planner import PlannerAgent
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer2_grounding.semantic_catalog import (
    load_semantic_catalog,
    resolve_semantic_binding,
)
from agentic_text2sql.layer3_generation.easy_compiler import GroundedEasyCompiler
from agentic_text2sql.layer3_generation.normalizer import CandidateNormalizer
from agentic_text2sql.layer4_validation.binding_validator import validate_sql_against_binding
from agentic_text2sql_eval.olist_acceptance import _rows_equal, load_olist_acceptance

ROOT = Path(__file__).resolve().parents[2]


class ModelCallForbidden:
    def generate_structured(self, **_: object) -> None:
        raise AssertionError("proof replay must not call a model")


def test_all_admitted_dev_regression_proofs_are_exact_and_diverse(tmp_path: Path) -> None:
    """Gold stays in the evaluator test; runtime sees only questions and schema metadata."""
    database = tmp_path / "olist.sqlite"
    shutil.copyfile(ROOT / "data/processed/olist.sqlite", database)
    catalog = SQLiteIntrospector().inspect(database, "olist")
    semantics = load_semantic_catalog(ROOT / "datasets/olist/semantic_catalog.yaml", catalog)
    cases = [
        case
        for case in load_olist_acceptance(ROOT / "evals/configs/olist-acceptance-60.jsonl")
        if case.partition in {"dev", "regression"}
    ]
    planner = PlannerAgent(  # type: ignore[arg-type]
        ModelCallForbidden(), ROOT / "configs/prompts/planner_v2.j2"
    )
    compiler = GroundedEasyCompiler(CandidateNormalizer())
    proof_kinds: set[str] = set()
    admitted = 0
    admitted_ids: set[str] = set()

    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        for case in cases:
            decomposition = Decomposer().decompose(case.question)
            binding = resolve_semantic_binding(
                case.question,
                decomposition,
                catalog,
                semantics,
            )
            if binding.status is not BindingStatus.PROVEN:
                continue
            links = SemanticLinkPlan(
                db_id="olist",
                catalog_hash=catalog.catalog_hash,
                required_tables=binding.required_tables,
                binding=binding,
            )
            context = SchemaContext(
                db_id="olist",
                selected_tables=list(binding.required_tables),
                selected_columns=list(binding.required_columns),
                joins=[],
                evidence=[],
                catalog_hash=catalog.catalog_hash,
            )
            plan = planner.plan_grounded(case.question, decomposition, links, context)
            candidate = compiler.compile(plan, catalog)

            assert candidate is not None
            assert validate_sql_against_binding(candidate.normalized_sql, binding) == ()
            actual = [list(row) for row in connection.execute(candidate.normalized_sql).fetchall()]
            expected = [list(row) for row in connection.execute(case.gold_sql).fetchall()]
            assert _rows_equal(
                actual,
                expected,
                order_matters=case.result_order_matters,
                tolerance=case.tolerance,
            ), case.id
            admitted += 1
            admitted_ids.add(case.id)
            if binding.frequency_ranking is not None:
                proof_kinds.add("frequency_ranking")
            else:
                assert binding.aggregate is not None
                proof_kinds.add(f"aggregate:{binding.aggregate.operator.value.casefold()}")
    finally:
        connection.close()

    assert admitted >= 5
    assert len(proof_kinds) >= 3
    assert {"olist_acc_035", "olist_acc_039", "olist_acc_040"} <= admitted_ids


def test_relational_proofs_reject_the_three_observed_incumbent_shapes() -> None:
    catalog = SQLiteIntrospector().inspect(ROOT / "data/processed/olist.sqlite", "olist")
    semantics = load_semantic_catalog(ROOT / "datasets/olist/semantic_catalog.yaml", catalog)
    observed = {
        "olist_acc_035": (
            "Top 5 danh mục tiếng Anh theo doanh thu sản phẩm cents, hòa thì tên tăng dần.",
            "SELECT p.product_category_name_english, SUM(oi.product_revenue_cents) "
            "FROM products_semantic p JOIN order_item_totals oi "
            "ON p.product_id = oi.product_id GROUP BY p.product_category_name_english "
            "ORDER BY 2 DESC, 1 ASC LIMIT 5",
        ),
        "olist_acc_039": (
            "Đếm đơn có tổng tiền đã trả lớn hơn tổng giá sản phẩm, "
            "dùng dữ liệu đã aggregate theo order.",
            "SELECT COUNT(*) FROM customer_order_facts "
            "WHERE (SELECT SUM(price_cents) FROM olist_order_items_dataset GROUP BY order_id) "
            "< (SELECT SUM(paid_value_cents) FROM order_payment_totals GROUP BY order_id)",
        ),
        "olist_acc_040": (
            "How many orders have both item totals and payment totals?",
            "SELECT COUNT(*) FROM olist_order_payments_dataset "
            "WHERE payment_value_cents IS NOT NULL",
        ),
    }
    for case_id, (question, incumbent_sql) in observed.items():
        binding = resolve_semantic_binding(
            question,
            Decomposer().decompose(question),
            catalog,
            semantics,
        )
        assert binding.status is BindingStatus.PROVEN, case_id
        assert binding.joins, case_id
        assert validate_sql_against_binding(incumbent_sql, binding), case_id


def test_post_recovery_certified_proofs_match_four_failed_results(tmp_path: Path) -> None:
    """The runtime compiles typed proofs; gold is opened only in this evaluator-side test."""
    database = tmp_path / "olist.sqlite"
    shutil.copyfile(ROOT / "data/processed/olist.sqlite", database)
    catalog = SQLiteIntrospector().inspect(database, "olist")
    semantics = load_semantic_catalog(ROOT / "datasets/olist/semantic_catalog.yaml", catalog)
    cases = {
        case.id: case
        for case in load_olist_acceptance(ROOT / "evals/configs/olist-acceptance-60.jsonl")
        if case.id in {"olist_acc_045", "olist_acc_046", "olist_acc_054", "olist_acc_059"}
    }
    planner = PlannerAgent(  # type: ignore[arg-type]
        ModelCallForbidden(), ROOT / "configs/prompts/planner_v2.j2"
    )
    compiler = GroundedEasyCompiler(CandidateNormalizer())

    with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        for case_id, case in cases.items():
            decomposition = Decomposer().decompose(case.question)
            binding = resolve_semantic_binding(case.question, decomposition, catalog, semantics)
            assert binding.status is BindingStatus.PROVEN, case_id
            links = SemanticLinkPlan(
                db_id="olist",
                catalog_hash=catalog.catalog_hash,
                required_tables=binding.required_tables,
                binding=binding,
            )
            context = SchemaContext(
                db_id="olist",
                selected_tables=list(binding.required_tables),
                selected_columns=list(binding.required_columns),
                joins=[],
                evidence=[],
                catalog_hash=catalog.catalog_hash,
            )
            plan = planner.plan_grounded(case.question, decomposition, links, context)
            candidate = compiler.compile(plan, catalog)
            assert candidate is not None, case_id
            assert validate_sql_against_binding(candidate.normalized_sql, binding) == (), case_id
            actual = [list(row) for row in connection.execute(candidate.normalized_sql).fetchall()]
            expected = [list(row) for row in connection.execute(case.gold_sql).fetchall()]
            assert _rows_equal(
                actual,
                expected,
                order_matters=case.result_order_matters,
                tolerance=case.tolerance,
            ), case_id
