"""Run the live, gold-separated Phase 2 Olist direct baseline."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from agentic_text2sql.adapters.llm.ollama_provider import OllamaProvider
from agentic_text2sql.layer1_reasoning.decomposer import Decomposer
from agentic_text2sql.layer1_reasoning.planner import PlannerAgent
from agentic_text2sql.layer1_reasoning.router import QueryRouter
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer3_generation.generator import GeneratorAgent
from agentic_text2sql.layer3_generation.normalizer import CandidateNormalizer
from agentic_text2sql.layer3_generation.prompt_builder import PromptBuilder
from agentic_text2sql.layer3_generation.service import GenerationService
from agentic_text2sql.layer4_validation.executor import ReadOnlySQLiteExecutor
from agentic_text2sql.layer4_validation.policy import SQLSafetyPolicy
from agentic_text2sql.layer6_application.query_service import DirectBaselineService
from agentic_text2sql.settings import Settings
from agentic_text2sql_eval.inference_runner import load_smoke_cases, run_inference
from agentic_text2sql_eval.report import evaluate_predictions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    settings = Settings()
    root = settings.project_root
    cases_path = args.cases or root / "evals/configs/olist-smoke-20.jsonl"
    predictions_path = args.predictions or root / "evals/predictions/olist-direct-p2.jsonl"
    report_path = args.report or root / "evals/reports/olist-direct-p2.json"
    source_database = settings.resolved_data_dir / "processed/olist.sqlite"
    with tempfile.TemporaryDirectory(prefix="agentic-text2sql-p2-") as temporary:
        database = Path(temporary) / "olist.sqlite"
        shutil.copyfile(source_database, database)
        catalog = SQLiteIntrospector().inspect(database, "olist")
        with OllamaProvider(settings) as provider:
            planner = PlannerAgent(provider, root / "configs/prompts/planner_v1.j2")
            generation = GenerationService(
                PromptBuilder(
                    root / "configs/prompts/generator_v1.j2",
                    root / "datasets/olist/business_glossary.yaml",
                ),
                GeneratorAgent(provider),
                CandidateNormalizer(),
                settings.ollama_model,
            )
            service = DirectBaselineService(
                router=QueryRouter(),
                decomposer=Decomposer(),
                planner=planner,
                generation=generation,
                policy=SQLSafetyPolicy(default_limit=200),
                executor=ReadOnlySQLiteExecutor(timeout_seconds=10, max_rows=200),
            )
            cases = load_smoke_cases(cases_path)
            predictions = run_inference(
                cases=cases,
                service=service,
                database=database,
                catalog=catalog,
                prediction_path=predictions_path,
            )
        report = evaluate_predictions(
            cases=cases,
            predictions=predictions,
            database=database,
            report_path=report_path,
        )
    print(json.dumps({key: value for key, value in report.items() if key != "details"}, indent=2))


if __name__ == "__main__":
    main()
