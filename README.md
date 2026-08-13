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

Gate evidence is recorded under [`docs/evidence`](docs/evidence), including the current
[`P5 application gate`](docs/evidence/p5_gate.md).

The application routes unsupported/write intents before model calls, creates a schema-agnostic
structured plan, grounds it against a pinned local index, generates one candidate, and sends every
candidate—including repairs—through the same read-only policy/executor. Correction is bounded to
one repair and remains opt-in. Gold SQL is loaded only by the evaluator after inference closes.

P5 adds one shared runtime path for CLI, FastAPI and Streamlit; a persistent SQLite run/trace/
feedback/catalog ledger; restart-safe SSE; and a five-workspace local SQL Observatory. Query
starters support smooth drag reordering with a keyboard-accessible fallback, while Run Inspector,
History, Benchmark Lab and System Center expose evidence without allowing browser-side SQL
execution or arbitrary database paths.
