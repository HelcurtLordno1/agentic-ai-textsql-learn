# Agentic Text-to-SQL — V5

[![CI](https://github.com/HelcurtLordno1/agentic-ai-textsql-learn/actions/workflows/ci.yml/badge.svg)](https://github.com/HelcurtLordno1/agentic-ai-textsql-learn/actions/workflows/ci.yml)

A local Text-to-SQL application for querying SQLite databases in natural language.
V5 includes a command-line interface, FastAPI service, Streamlit workspace, read-only
SQL execution, bounded recovery and monitored local model execution.

The core runs with Ollama and does not require paid provider APIs or API keys.

## What you can do

- Register a local SQLite database and ask analytical questions.
- Inspect generated SQL, result previews and execution status.
- Use the CLI, local API or web interface.
- Keep application history and generated artifacts on your machine.
- Run deterministic checks without downloading datasets or starting a model.

## V5 evaluation snapshot

| Local evaluation | Result |
| --- | ---: |
| Spider, selected 200-case set | 143/200 — 71.50% |
| Olist, 60-case application set | 50/60 — 83.33% |

Both workloads completed. These are measurements from a specific local setup;
execution success does not guarantee a correct answer. The Spider result is not
an official hidden-test leaderboard score.

## Requirements

For installation and tests:

- Python 3.12
- [uv](https://docs.astral.sh/uv/), Git and Make
- Linux or WSL2

For model execution, install Ollama and the models configured in
[configs/models.yaml](configs/models.yaml). The included laptop monitoring tools
also require NVIDIA telemetry; the Windows/WSL configuration uses PowerShell interop.
Model-free checks do not require a GPU or a running Ollama service.

## Install and verify

```bash
git clone --branch main https://github.com/HelcurtLordno1/agentic-ai-textsql-learn.git
cd agentic-ai-textsql-learn
make sync
make check
```

Dependencies are pinned in `uv.lock`. `make sync` installs the UI extra and development
tools. `make check` runs lint, formatting, type checks and tests, excluding the explicit
local-model test marker. Dataset integrations skip when their data is not installed.

## Configure the application

For the V5 application configuration:

```bash
cp .env.v5.example .env
```

Update `OLLAMA_BASE_URL` for your local Ollama endpoint. If Ollama runs on Windows
and the application runs in WSL, use the reachable Windows host/gateway address.
The general configuration template is [.env.example](.env.example).

Install the configured models in the Ollama installation used by that endpoint:

```bash
ollama pull qwen3:14b-q4_K_M
ollama pull bge-m3:latest
```

Keep model identities compatible with `configs/models.yaml`. Downloading weights
is separate from running inference. Machine-specific `.env` files and model weights
are not included in Git.

## Prepare example data

The optional Olist workflow downloads the pinned source, builds SQLite and validates it:

```bash
uv run --frozen --extra ui --group dev text2sql data download olist
uv run --frozen --extra ui --group dev text2sql data build olist
uv run --frozen --extra ui --group dev text2sql data validate olist
uv run --frozen --extra ui --group dev text2sql ingest --db data/processed/olist.sqlite --db-id olist
```

You can register another compatible local SQLite database with `text2sql ingest`.
Registration and semantic index construction are separate operations. Data and indexes
are prepared locally and must match the database used for a request.

## Run the local interface

All model requests must run through a monitored launcher. On the approved Windows/WSL
CPU configuration, start the API from the repository root:

```bash
TEXT2SQL_MONITOR_WINDOWS_HOST=true uv run --frozen --extra ui --group dev python -m scripts.run_guarded_local \
  --profile qwen14b-cpu600-stable \
  --stop-file data/artifacts/v5-api.resource-stop.json \
  -- .venv/bin/text2sql serve
```

In another terminal, start the UI:

```bash
uv run --frozen --extra ui --group dev streamlit run apps/streamlit_app.py
```

The API binds to localhost by default. Model requests require a compatible database,
installed models and safe resources. A workflow may stop with a typed error when
input, validation or resource limits cannot be satisfied.

## Model execution requirements

Use the guarded entrypoints for model requests, index preparation and evaluation.
They require continuous resource monitoring, explicit bounded GPU offload, one workload
at a time, model unload and cooldown. Do not run generation and embedding concurrently.

The supplied laptop profile is machine-specific. Apply its approved hardware settings
before starting. A sensor failure or resource breach stops the workload and preserves
a stop latch; do not delete the latch or automatically retry a stopped run.

Inspect the available operational commands without starting inference:

```bash
uv run --frozen --extra ui --group dev text2sql --help
uv run --frozen --extra ui --group dev python -m scripts.run_guarded_local --help
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks --help
```

## Local files and repository contents

The public source includes application code, tests, configuration examples, dependency
locks and setup tools. Downloaded datasets, generated databases, model weights, indexes,
predictions, traces and secrets are excluded from Git. Keep these local, and use fresh
output paths when changing code, settings or model identities.

## License and attribution

Source code is licensed under [MIT](LICENSE). Dependencies, models and datasets retain
their own licenses. Olist data is attributed to Olist; the project's pinned dataset
metadata records CC BY-NC-SA 4.0. Raw Olist data is not redistributed in this repository.
