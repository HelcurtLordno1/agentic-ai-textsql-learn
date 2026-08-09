"""Build P3 Olist/Spider indexes and emit separate retrieval reports."""

from __future__ import annotations

import json
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from agentic_text2sql.adapters.embeddings.ollama_embeddings import OllamaEmbeddingClient
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer2_grounding.service import IndexService
from agentic_text2sql.settings import Settings
from agentic_text2sql_eval.schema_metrics import extract_gold_schema, score_retrieval

ROOT = Path(__file__).resolve().parents[1]
MODEL = "bge-m3:latest"


def semantic_aliases() -> dict[str, str]:
    payload = yaml.safe_load((ROOT / "datasets/olist/business_glossary.yaml").read_text())
    aliases: dict[str, str] = {}
    for name, concept in payload["concepts"].items():
        text = f"{name} {concept.get('definition', '')} {concept.get('canonical_expression', '')}"
        expression = str(concept.get("canonical_expression", ""))
        for identifier in expression.replace("(", " ").replace(")", " ").split():
            cleaned = identifier.strip(",><=")
            if "." in cleaned:
                aliases[cleaned] = text
    return aliases


def mini_100(dev: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in dev:
        grouped[str(case["db_id"])].append(case)
    selected = []
    for db_id in sorted(grouped):
        ranked = sorted(
            grouped[db_id],
            key=lambda case: (
                sum(
                    str(case["query"]).upper().count(word)
                    for word in (" JOIN ", "SELECT ", "GROUP BY", "UNION", "INTERSECT", "EXCEPT")
                ),
                str(case["question"]),
            ),
        )
        positions = [round(index * (len(ranked) - 1) / 4) for index in range(5)]
        selected.extend(ranked[position] for position in positions)
    if len(selected) != 100:
        raise RuntimeError(f"expected 100 stratified cases, got {len(selected)}")
    return selected


def evaluate(
    cases: list[dict[str, Any]], retrievers: dict[str, Any], query_cache: dict[str, list[float]]
) -> dict[str, Any]:
    modes = ("bm25", "dense", "hybrid")
    rows: dict[str, list[dict[str, float]]] = {mode: [] for mode in modes}
    latencies: dict[str, list[float]] = {mode: [] for mode in modes}
    tokens: dict[str, list[int]] = {mode: [] for mode in modes}
    for case in cases:
        question, db_id = str(case["question"]), str(case["db_id"])
        gold = extract_gold_schema(str(case["query"]))
        for mode in modes:
            started = time.perf_counter()
            result = retrievers[db_id].retrieve(question, mode=mode, top_k=20, token_budget=1000)
            latencies[mode].append((time.perf_counter() - started) * 1000)
            tokens[mode].append(result.estimated_tokens)
            rows[mode].append(score_retrieval(result, gold))
    return {
        "case_count": len(cases),
        "modes": {
            mode: {
                **{
                    metric: round(statistics.fmean(row[metric] for row in rows[mode]), 6)
                    for metric in rows[mode][0]
                },
                "avg_context_tokens": round(statistics.fmean(tokens[mode]), 2),
                "p95_retrieval_ms": round(sorted(latencies[mode])[int(len(cases) * 0.95) - 1], 3),
            }
            for mode in modes
        },
        "query_embedding_cache_entries": len(query_cache),
    }


def prefill_queries(
    cases: list[dict[str, Any]], cache: dict[str, list[float]], client: OllamaEmbeddingClient
) -> None:
    missing = sorted({str(case["question"]) for case in cases} - cache.keys())
    if missing:
        vectors = client.embed(missing, batch_size=32)
        cache.update(zip(missing, vectors, strict=True))


def main() -> None:
    settings = Settings()
    client = OllamaEmbeddingClient(settings.ollama_base_url, MODEL)
    index_root = ROOT / "data/indexes/p3"
    service = IndexService(index_root, MODEL, lambda texts: client.embed(texts, batch_size=32))
    introspector = SQLiteIntrospector()
    query_cache: dict[str, list[float]] = {}

    def embed_query(text: str) -> list[float]:
        if text not in query_cache:
            query_cache[text] = client.embed([text])[0]
        return query_cache[text]

    olist = introspector.inspect(ROOT / "data/processed/olist.sqlite", "olist")
    raw_manifest = service.build(olist)
    raw = service.load("olist", embed_query)
    smoke = [
        json.loads(line)
        for line in (ROOT / "evals/configs/olist-smoke-20.jsonl").read_text().splitlines()
    ]
    olist_cases = [
        {"db_id": "olist", "question": row["question"], "query": row["gold_sql"]}
        for row in smoke
        if row.get("gold_sql")
    ]
    prefill_queries(olist_cases, query_cache, client)
    raw_report = evaluate(olist_cases, {"olist": raw}, query_cache)
    semantic_root = ROOT / "data/indexes/p3_semantic"
    semantic_service = IndexService(
        semantic_root, MODEL, lambda texts: client.embed(texts, batch_size=32)
    )
    semantic_manifest = semantic_service.build(olist, semantic_aliases())
    semantic = semantic_service.load("olist", embed_query)
    semantic_report = evaluate(olist_cases, {"olist": semantic}, query_cache)

    spider_root = ROOT / "data/raw/spider/spider_data"
    dev = json.loads((spider_root / "dev.json").read_text())
    mini = mini_100(dev)
    prefill_queries(mini, query_cache, client)
    spider_retrievers = {}
    manifests = []
    for db_id in sorted({str(case["db_id"]) for case in mini}):
        database = spider_root / "database" / db_id / f"{db_id}.sqlite"
        catalog = introspector.inspect(database, db_id)
        manifests.append(service.build(catalog))
        spider_retrievers[db_id] = service.load(db_id, embed_query)
    spider_report = evaluate(mini, spider_retrievers, query_cache)
    output = ROOT / "data/artifacts/p3"
    output.mkdir(parents=True, exist_ok=True)
    (output / "olist_retrieval.json").write_text(
        json.dumps(
            {
                "raw": raw_report,
                "semantic": semantic_report,
                "raw_manifest": raw_manifest,
                "semantic_manifest": semantic_manifest,
            },
            indent=2,
            sort_keys=True,
        )
    )
    (output / "spider_mini_100_schema_recall.json").write_text(
        json.dumps(
            {
                **spider_report,
                "database_count": len(spider_retrievers),
                "index_manifests": manifests,
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(
        json.dumps(
            {
                "olist_raw": raw_report["modes"],
                "olist_semantic": semantic_report["modes"],
                "spider": spider_report["modes"],
                "spider_databases": len(spider_retrievers),
            },
            indent=2,
        )
    )
    client.close()


if __name__ == "__main__":
    main()
