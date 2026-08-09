# Agentic Text-to-SQL

A fully local, free, six-layer agentic text-to-SQL learning and portfolio project.
The canonical specification and completion ledger is
[`realistic_project_creation_codex.md`](realistic_project_creation_codex.md).

## Verified setup and Olist data foundation

```bash
uv sync --frozen --group dev
uv run ruff check .
uv run mypy src
uv run pytest
uv run text2sql doctor
uv run text2sql ollama-smoke
uv run text2sql data download olist
uv run text2sql data build olist
uv run text2sql data validate olist
uv run python scripts/run_smoke.py
```

The ordinary CI suite uses fake transports and a deterministic synthetic database; it does not
require Olist, Kaggle, a GPU, or a running model. Olist integration tests run automatically when
`data/processed/olist.sqlite` exists and otherwise skip. `ollama-smoke` is the explicit local model
acceptance test.

The Olist build verifies the pinned archive and all CSV hashes/headers/counts, stores money as raw
decimal text plus integer cents, checks integrity/FKs, builds grain-safe semantic views, and only
then atomically publishes SQLite. Raw Olist data and the 175 MiB generated database stay ignored.

## Scope and licensing

Project source code is MIT licensed. Dataset and model licenses are separate. Olist raw files,
generated databases, indexes, and run artifacts are intentionally excluded from Git. See
[`data/README.md`](data/README.md) and [`docs/data/license_and_attribution.md`](docs/data/license_and_attribution.md).

Gate evidence: [`docs/evidence/p0_gate.md`](docs/evidence/p0_gate.md) and
[`docs/evidence/p1_gate.md`](docs/evidence/p1_gate.md), then
[`docs/evidence/p2_gate.md`](docs/evidence/p2_gate.md) and the current hardened
[`docs/evidence/p3_1_gate.md`](docs/evidence/p3_1_gate.md).

The verified Phase 2 direct baseline routes unsupported/write intents before model calls, creates a
schema-agnostic structured plan, generates one SQL candidate from the full Olist schema, and sends
every candidate through the Phase 1 policy/executor. Gold SQL is loaded only by the evaluator after
inference. This baseline deliberately has no retrieval and no correction yet.

P3.1 adds pinned BGE-M3/FAISS + BM25 retrieval, immutable checksum-verified index versions,
plan-aware minimal FK closure and budgeted grounded prompts. Qualified retrieval is validated on
100 Spider regression cases plus a disjoint 100-case holdout. Grounded Olist generation matches the
full-schema 14/18 baseline while reducing estimated prompt tokens by 41.96%; its extra local
embedding latency is reported rather than hidden. Correction remains outside the current gate.
