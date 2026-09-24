"""Offline, model-free schema-context ablation on a development manifest.

The two contexts are built before benchmark SQL is opened by the evaluator.
This script never calls Ollama and does not write per-case predictions.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import yaml

from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.retrieval import SchemaContext
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer2_grounding.schema_linker import link_schema
from agentic_text2sql.layer2_grounding.service import IndexService
from agentic_text2sql_eval.schema_metrics import extract_gold_schema, score_retrieval
from agentic_text2sql_eval.spider_adapter import load_manifest_cases

ROOT = Path(__file__).resolve().parents[1]


def _summary(
    contexts: list[SchemaContext], scores: list[dict[str, float | None]]
) -> dict[str, float | int]:
    def micro(hit: str, total: str) -> float:
        return round(
            sum(float(row[hit] or 0) for row in scores)
            / max(1, sum(float(row[total] or 0) for row in scores)),
            6,
        )

    return {
        "cases": len(contexts),
        "table_recall": micro("table_hits", "table_gold"),
        "column_recall": micro("column_hits", "column_gold"),
        "fk_recall": micro("foreign_key_hits", "foreign_key_gold"),
        "single_table_contexts": sum(len(context.selected_tables) == 1 for context in contexts),
        "mean_context_tokens": round(statistics.fmean(c.estimated_tokens for c in contexts), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "evals/configs/spider-mini-100.json",
    )
    args = parser.parse_args()
    spider = ROOT / "data/raw/spider/spider_data"
    cases = load_manifest_cases(spider / "dev.json", args.manifest)
    model_config = yaml.safe_load((ROOT / "configs/models.yaml").read_text(encoding="utf-8"))
    digest = str(model_config["embedding"]["digest"])
    index = IndexService(
        ROOT / "data/indexes/p3_1_semantic",
        "bge-m3:latest",
        digest,
        lambda _: (_ for _ in ()).throw(RuntimeError("embedding is disabled in offline ablation")),
    )
    introspector = SQLiteIntrospector()
    catalogs = {}
    retrievers = {}
    for db_id in sorted({str(case["db_id"]) for case in cases}):
        database = spider / "database" / db_id / f"{db_id}.sqlite"
        catalogs[db_id] = introspector.inspect(database, db_id)
        retrievers[db_id] = index.load(
            db_id,
            lambda _: (_ for _ in ()).throw(
                RuntimeError("embedding is disabled in offline ablation")
            ),
        )

    contexts: dict[str, list[SchemaContext]] = {"legacy": [], "coverage": []}
    elapsed: dict[str, float] = {"legacy": 0, "coverage": 0}
    for case in cases:
        question, db_id = str(case["question"]), str(case["db_id"])
        catalog = catalogs[db_id]
        retrieval = retrievers[db_id].retrieve(question, mode="bm25", top_k=20)
        plan = LogicalPlan(question_language="en", task_type="lookup", required_concepts=[question])
        for mode in ("legacy", "coverage"):
            started = time.perf_counter()
            if mode == "legacy" and not retrieval.candidates:
                context = SchemaContext(
                    db_id=db_id,
                    selected_tables=[],
                    selected_columns=[],
                    joins=[],
                    evidence=[],
                    catalog_hash=catalog.catalog_hash,
                )
            else:
                context = link_schema(
                    plan,
                    retrieval,
                    catalog,
                    token_budget=1200,
                    mode=mode,
                    question=question,
                )
            elapsed[mode] += time.perf_counter() - started
            contexts[mode].append(context)

    # Gold SQL is accessed only after both predictions have been frozen in memory.
    scores = {mode: [] for mode in contexts}
    for position, case in enumerate(cases):
        gold = extract_gold_schema(str(case["query"]), catalogs[str(case["db_id"])])
        for mode in contexts:
            scores[mode].append(score_retrieval(contexts[mode][position], gold))
    output = {
        "manifest": str(args.manifest.resolve().relative_to(ROOT)),
        "retrieval_mode": "bm25",
        "top_k": 20,
        "token_budget": 1200,
        "modes": {
            mode: {
                **_summary(contexts[mode], scores[mode]),
                "total_linker_seconds": round(elapsed[mode], 3),
            }
            for mode in contexts
        },
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
