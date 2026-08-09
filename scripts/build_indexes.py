"""Build hardened indexes and emit qualified P3.1 retrieval reports."""

from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

import yaml

from agentic_text2sql.adapters.embeddings.ollama_embeddings import OllamaEmbeddingClient
from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.retrieval import SchemaContext
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector, catalog_subset
from agentic_text2sql.layer2_grounding.schema_linker import link_schema
from agentic_text2sql.layer2_grounding.service import IndexService
from agentic_text2sql.settings import Settings
from agentic_text2sql_eval.schema_metrics import extract_gold_schema, score_retrieval
from agentic_text2sql_eval.spider_adapter import load_manifest_cases

ROOT = Path(__file__).resolve().parents[1]
MODEL = "bge-m3:latest"
MODEL_DIGEST = "7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab"
METRICS = ("table_recall", "column_recall", "context_precision", "schema_recall")


def semantic_aliases() -> dict[str, str]:
    payload = yaml.safe_load((ROOT / "datasets/olist/business_glossary.yaml").read_text())
    aliases: dict[str, str] = {}
    for name, concept in payload["concepts"].items():
        text = f"{name} {concept.get('definition', '')} {concept.get('canonical_expression', '')}"
        for field in ("canonical_expression", "identity_column"):
            expression = str(concept.get(field, ""))
            for identifier in expression.replace("(", " ").replace(")", " ").split():
                cleaned = identifier.strip(",><=")
                if "." in cleaned:
                    aliases[cleaned] = text
    return aliases


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    return sorted(values)[max(0, math.ceil(len(values) * percentile) - 1)]


def load_or_measure_queries(
    questions: set[str], client: OllamaEmbeddingClient, cache_path: Path
) -> tuple[dict[str, list[float]], dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = (
        json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    )
    measured = []
    ordered_questions = sorted(questions)

    def checkpoint() -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")
        temporary.replace(cache_path)

    for question in ordered_questions:
        key = f"{MODEL_DIGEST}:{question}"
        if key not in cache:
            started = time.perf_counter()
            vector = client.embed([question])[0]
            elapsed = (time.perf_counter() - started) * 1000
            measured.append(elapsed)
            cache[key] = {"vector": vector, "embedding_ms": elapsed}
            checkpoint()
    checkpoint()
    selected = {question: cache[f"{MODEL_DIGEST}:{question}"]["vector"] for question in questions}
    recorded = [
        float(cache[f"{MODEL_DIGEST}:{question}"]["embedding_ms"]) for question in questions
    ]
    first_recorded = float(cache[f"{MODEL_DIGEST}:{ordered_questions[0]}"]["embedding_ms"])
    return selected, {
        "model_digest": MODEL_DIGEST,
        "fresh_measurement_count": len(measured),
        "first_recorded_request_ms": round(first_recorded, 3),
        "recorded_unique_request_p50_ms": round(_percentile(recorded, 0.50), 3),
        "recorded_unique_request_p95_ms": round(_percentile(recorded, 0.95), 3),
    }


def _evaluation_plan(question: str) -> LogicalPlan:
    return LogicalPlan(question_language="en", task_type="lookup", required_concepts=[question])


def _aggregate(
    rows: list[dict[str, float | None]], tokens: list[int], latency: list[float]
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "macro": {
            metric: round(
                statistics.fmean(float(row[metric]) for row in rows if row[metric] is not None),
                6,
            )
            for metric in METRICS
        },
        "micro": {
            "table_recall": round(
                sum(float(row["table_hits"]) for row in rows)
                / max(1, sum(float(row["table_gold"]) for row in rows)),
                6,
            ),
            "column_recall": round(
                sum(float(row["column_hits"]) for row in rows)
                / max(1, sum(float(row["column_gold"]) for row in rows)),
                6,
            ),
            "foreign_key_recall": round(
                sum(float(row["foreign_key_hits"]) for row in rows)
                / max(1, sum(float(row["foreign_key_gold"]) for row in rows)),
                6,
            ),
            "join_edge_recall": round(
                sum(float(row["join_edge_hits"]) for row in rows)
                / max(1, sum(float(row["join_edge_gold"]) for row in rows)),
                6,
            ),
        },
        "join_case_count": sum(row["join_edge_recall"] is not None for row in rows),
        "foreign_key_case_count": sum(row["foreign_key_recall"] is not None for row in rows),
        "foreign_key_recall_on_join_cases": round(
            statistics.fmean(
                float(row["foreign_key_recall"])
                for row in rows
                if row["foreign_key_recall"] is not None
            ),
            6,
        )
        if any(row["foreign_key_recall"] is not None for row in rows)
        else None,
        "join_edge_recall_on_join_cases": round(
            statistics.fmean(
                float(row["join_edge_recall"])
                for row in rows
                if row["join_edge_recall"] is not None
            ),
            6,
        )
        if any(row["join_edge_recall"] is not None for row in rows)
        else None,
        "avg_context_tokens": round(statistics.fmean(tokens), 2),
        "ranking_and_linking_latency_ms": {
            "p50": round(_percentile(latency, 0.5), 3),
            "p95": round(_percentile(latency, 0.95), 3),
        },
    }
    return report


def evaluate(
    cases: list[dict[str, Any]],
    retrievers: dict[str, Any],
    catalogs: dict[str, CatalogSnapshot],
    gold_catalogs: dict[str, CatalogSnapshot] | None = None,
) -> dict[str, Any]:
    gold_catalogs = gold_catalogs or catalogs
    report: dict[str, Any] = {"case_count": len(cases), "modes": {}}
    for mode in ("bm25", "dense", "hybrid"):
        report["modes"][mode] = {}
        for top_k in (5, 10, 20):
            candidate_rows: list[dict[str, float | None]] = []
            linked_rows: list[dict[str, float | None]] = []
            candidate_tokens: list[int] = []
            linked_tokens: list[int] = []
            latencies: list[float] = []
            for case in cases:
                question, db_id = str(case["question"]), str(case["db_id"])
                catalog = catalogs[db_id]
                gold = extract_gold_schema(str(case["query"]), gold_catalogs[db_id])
                started = time.perf_counter()
                retrieval = retrievers[db_id].retrieve(question, mode=mode, top_k=top_k)
                if retrieval.candidates:
                    linked = link_schema(
                        _evaluation_plan(question), retrieval, catalog, token_budget=1000
                    )
                else:
                    linked = SchemaContext(
                        db_id=db_id,
                        selected_tables=[],
                        selected_columns=[],
                        joins=[],
                        evidence=[],
                        catalog_hash=catalog.catalog_hash,
                    )
                latencies.append((time.perf_counter() - started) * 1000)
                candidate_rows.append(score_retrieval(retrieval, gold))
                linked_rows.append(score_retrieval(linked, gold))
                candidate_tokens.append(retrieval.estimated_tokens)
                linked_tokens.append(linked.estimated_tokens)
            report["modes"][mode][f"at_{top_k}"] = {
                "candidate": _aggregate(candidate_rows, candidate_tokens, latencies),
                "linked": _aggregate(linked_rows, linked_tokens, latencies),
            }
    return report


def main() -> None:
    settings = Settings()
    client = OllamaEmbeddingClient(settings.ollama_base_url, MODEL)
    actual_digest = client.model_digest()
    if actual_digest != MODEL_DIGEST:
        raise RuntimeError(f"BGE-M3 digest mismatch: expected {MODEL_DIGEST}, got {actual_digest}")
    introspector = SQLiteIntrospector()
    spider_root = ROOT / "data/raw/spider/spider_data"
    mini = load_manifest_cases(
        spider_root / "dev.json", ROOT / "evals/configs/spider-mini-100.json"
    )
    holdout = load_manifest_cases(
        spider_root / "dev.json", ROOT / "evals/configs/spider-holdout-100.json"
    )
    smoke = [
        json.loads(line)
        for line in (ROOT / "evals/configs/olist-smoke-20.jsonl").read_text().splitlines()
    ]
    olist_cases = [
        {"db_id": "olist", "question": row["question"], "query": row["gold_sql"]}
        for row in smoke
        if row.get("gold_sql")
    ]
    vectors, embedding_latency = load_or_measure_queries(
        {str(case["question"]) for case in [*olist_cases, *mini, *holdout]},
        client,
        ROOT / "data/artifacts/p3_1/query_embeddings.json",
    )

    def embed_query(text: str) -> list[float]:
        return vectors[text]

    index_root = ROOT / "data/indexes/p3_1"
    service = IndexService(
        index_root, MODEL, MODEL_DIGEST, lambda texts: client.embed(texts, batch_size=32)
    )
    semantic_olist = introspector.inspect(ROOT / "data/processed/olist.sqlite", "olist")
    olist = catalog_subset(semantic_olist, kinds={"table"})
    raw_manifest = service.build(olist)
    olist_retriever = service.load("olist", embed_query)
    olist_report = evaluate(
        olist_cases,
        {"olist": olist_retriever},
        {"olist": olist},
        {"olist": semantic_olist},
    )
    semantic_service = IndexService(
        ROOT / "data/indexes/p3_1_semantic",
        MODEL,
        MODEL_DIGEST,
        lambda texts: client.embed(texts, batch_size=32),
    )
    semantic_manifest = semantic_service.build(semantic_olist, semantic_aliases())
    semantic_report = evaluate(
        olist_cases,
        {"olist": semantic_service.load("olist", embed_query)},
        {"olist": semantic_olist},
    )
    catalogs: dict[str, CatalogSnapshot] = {}
    retrievers = {}
    manifests = []
    for db_id in sorted({str(case["db_id"]) for case in mini}):
        database = spider_root / "database" / db_id / f"{db_id}.sqlite"
        catalog = introspector.inspect(database, db_id)
        catalogs[db_id] = catalog
        manifests.append(service.build(catalog).model_dump(mode="json"))
        retrievers[db_id] = service.load(db_id, embed_query)
    spider_report = evaluate(mini, retrievers, catalogs)
    holdout_report = evaluate(holdout, retrievers, catalogs)
    output = ROOT / "data/artifacts/p3_1"
    output.mkdir(parents=True, exist_ok=True)
    (output / "olist_retrieval.json").write_text(
        json.dumps(
            {
                "raw": olist_report,
                "semantic": semantic_report,
                "raw_manifest": raw_manifest.model_dump(mode="json"),
                "semantic_manifest": semantic_manifest.model_dump(mode="json"),
                "query_embedding_latency": embedding_latency,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "spider_mini_100_schema_recall.json").write_text(
        json.dumps(
            {
                **spider_report,
                "unique_case_count": len(
                    {
                        str(case["question"]) + str(case["db_id"]) + str(case["query"])
                        for case in mini
                    }
                ),
                "database_count": len(retrievers),
                "query_embedding_latency": embedding_latency,
                "index_manifests": manifests,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "spider_holdout_100_schema_recall.json").write_text(
        json.dumps(
            {
                **holdout_report,
                "unique_case_count": len(
                    {
                        str(case["question"]) + str(case["db_id"]) + str(case["query"])
                        for case in holdout
                    }
                ),
                "database_count": len(retrievers),
                "query_embedding_latency": embedding_latency,
                "untouched_before_p3_1_freeze": True,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "olist": olist_report["modes"],
                "spider": spider_report["modes"],
                "spider_holdout": holdout_report["modes"],
                "embedding_latency": embedding_latency,
            },
            indent=2,
        )
    )
    client.close()


if __name__ == "__main__":
    main()
