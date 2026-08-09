# Gate P3 evidence — 2026-08-09

> Historical evidence only. A later audit found duplicate-subset, unqualified-metric, FK-denominator
> and latency-boundary defects. Corrected implementation and current numbers are in
> `docs/evidence/p3_1_gate.md`; do not use the P3 figures below as current benchmark claims.

## Implemented Layer 2

Gate P3 implements stable catalog documents, identifier-aware BM25, BGE-M3 embeddings through the
local Ollama API, normalized cosine search with FAISS CPU, weighted reciprocal-rank fusion, bounded
FK expansion/context packing, and a typed deterministic schema linker. Runtime package
`agentic_text2sql` has no dependency on gold SQL or `agentic_text2sql_eval`.

Every database bundle contains `catalog.json`, table/column/relationship JSONL, `documents.jsonl`,
`faiss.index`, `bm25.pkl`, and a checksum manifest. A document cache key includes model ID,
document-template version, and retrieval text. Loading verifies every artifact checksum and rejects
documents from another `db_id`. Unit tests rebuild the same catalog twice and verify identical
catalog/file hashes, reload behavior, corruption rejection, and the hard context budget.

## Dataset pin and evaluation protocol

Spider is downloaded only by `scripts/download_spider.py` from the archive linked by the official
Spider site. The accepted archive SHA-256 is
`00636695dabed6b5f4b8328a16b13e069a2f16591d5efcce57660669c85b121b`; raw data stays ignored.
The extracted dev split has 1,034 cases across 20 database domains. The fixed mini-100 takes five
complexity-spread cases per sorted domain. Gold tables, columns, and join edges are inferred with
SQLGlot only inside `agentic_text2sql_eval` after retrieval.

Command:

```bash
OLLAMA_BASE_URL=http://<local-ollama-host>:11434 uv run python scripts/build_indexes.py
```

Model: local `bge-m3:latest`. Indexes were built and checksum-reloaded for Olist plus all 20 Spider
dev domains (the DoD minimum is five). Reports are generated under ignored
`data/artifacts/p3/olist_retrieval.json` and
`data/artifacts/p3/spider_mini_100_schema_recall.json`.

## Retrieval results

Olist raw-catalog smoke set (18 gold-query cases, top 20, budget 1,000 estimated tokens):

| Mode | Table recall | Column recall | FK recall | Schema recall | Avg tokens |
|---|---:|---:|---:|---:|---:|
| BM25 | 0.740741 | 0.650000 | 0.888889 | 0.717593 | 359.78 |
| Dense | 0.972222 | 0.764815 | 0.972222 | 0.889815 | 496.06 |
| Hybrid | 0.972222 | 0.764815 | 0.972222 | 0.889815 | 496.06 |

The semantic-glossary ablation did not improve recall on this small set: hybrid schema recall stayed
0.889815 while average context grew from 496.06 to 531.72 tokens. This is retained as a truthful
negative ablation; semantic text is not claimed as a win.

Spider fixed mini-100 across 20 domains:

| Mode | Table recall | Column recall | FK recall | Schema recall | Context precision | Avg tokens |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 0.755000 | 0.505714 | 0.765000 | 0.640333 | 0.255591 | 186.18 |
| Dense | 0.790000 | 0.560310 | 0.815000 | 0.687179 | 0.204693 | 272.12 |
| Hybrid | 0.790000 | 0.560310 | 0.815000 | 0.687179 | 0.204693 | 272.12 |

The initial BM25-heavy fusion scored 0.683690, below dense 0.687179, so it was rejected. The final
guarded fusion uses dense weight 1.0 and BM25 weight 0.01: hybrid now equals the best single
retriever on Olist and Spider, satisfying the explicit retention rule without overstating a gain.
All measured contexts remained below the 1,000-token evaluation budget.

## Final verification

`make check` result:

- Ruff lint: pass;
- Ruff format: 159 files pass;
- mypy strict: 95 source files, no issues;
- pytest excluding explicit live-model marker: 117 passed, 1 deselected;
- focused Layer 2 tests: 6 passed;
- live retrieval reports: 18 Olist cases and 100 Spider cases, 20 Spider databases.

Gate P3 is `VERIFIED`. Safe profiling remains optional and later SQL correction/application gates
remain out of scope.
