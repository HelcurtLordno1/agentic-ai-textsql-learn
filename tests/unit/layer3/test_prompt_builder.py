from pathlib import Path

from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer3_generation.prompt_builder import PromptBuilder

ROOT = Path(__file__).resolve().parents[3]


def test_prompt_contains_contract_catalog_glossary_and_version_inputs() -> None:
    database = ROOT / "data/samples/synthetic_commerce_tiny.sqlite"
    catalog = SQLiteIntrospector().inspect(database, "synthetic")
    plan = LogicalPlan(
        question_language="en",
        task_type="aggregation",
        metrics=["order count"],
        required_concepts=["orders"],
    )
    prompt = PromptBuilder(
        ROOT / "configs/prompts/generator_v1.j2",
        ROOT / "datasets/olist/business_glossary.yaml",
    ).build("How many orders?", plan, catalog)
    assert "TABLE orders(" in prompt
    assert catalog.catalog_hash in prompt
    assert "product_revenue" in prompt
    assert '"confidence"' in prompt
    assert "Never use DML" in prompt
