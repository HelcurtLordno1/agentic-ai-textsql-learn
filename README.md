# Agentic Text-to-SQL

[![CI](https://github.com/HelcurtLordno1/agentic-ai-textsql-learn/actions/workflows/ci.yml/badge.svg)](https://github.com/HelcurtLordno1/agentic-ai-textsql-learn/actions/workflows/ci.yml)

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
uv sync --frozen --extra ui --group dev
uv run text2sql ingest --db data/processed/olist.sqlite --db-id olist
uv run text2sql serve
# In a second terminal:
uv run streamlit run apps/streamlit_app.py
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

Gate evidence is recorded under [`docs/evidence`](docs/evidence), including the
[`P5 application gate`](docs/evidence/p5_gate.md),
[`P5.1 laptop hardening`](docs/evidence/p5_1_gate.md), and the P6 release evidence once its guarded
benchmark is complete.

The application routes unsupported/write intents before model calls, creates a schema-agnostic
structured plan, grounds it against a pinned local index, generates one candidate, and sends every
candidate—including repairs—through the same read-only policy/executor. Correction is bounded to
one repair and remains opt-in. Gold SQL is loaded only by the evaluator after inference closes.

P5 adds one shared runtime path for CLI, FastAPI and Streamlit; a persistent SQLite run/trace/
feedback/catalog ledger; restart-safe SSE; and a five-workspace local SQL Observatory. Query
starters support smooth drag reordering with a keyboard-accessible fallback, while Run Inspector,
History, Benchmark Lab and System Center expose evidence without allowing browser-side SQL
execution or arbitrary database paths.

## Gate P6 release evaluation

P6 pins every Spider dev row, `dev.json`, `tables.json`, and all 20 SQLite databases by SHA-256.
Inference checkpoints before any gold-aware evaluation; generated predictions and detailed reports
remain ignored. Start the bounded Ollama supervisor, then create/verify the manifest and run the
resumable release:

```bash
uv run python scripts/serve_ollama_guarded.py --profile acceptance-safe
uv run python scripts/run_benchmark.py --create-manifest
OLLAMA_BASE_URL=http://127.0.0.1:11434 TEXT2SQL_OLLAMA_NUM_GPU=6 \
  uv run python scripts/run_benchmark.py --correction --resume --max-new-cases 1
# Remove --max-new-cases only after the pilot is healthy.
OLLAMA_BASE_URL=http://127.0.0.1:11434 TEXT2SQL_OLLAMA_NUM_GPU=6 \
  uv run python scripts/run_guarded_spider.py \
  --profile interactive-balanced --batch-size 10 --cooldown-seconds 20 \
  --predictions evals/predictions/spider-p6-1034-gpu6.jsonl \
  --report evals/reports/spider-p6-1034.json
```

Benchmark Lab renders Olist and Spider in separate tabs. Spider reports execution equivalence,
complexity slices, failure taxonomy, latency, manifest identity and explicit limitations; it is not
presented as an official hidden-test leaderboard score.
