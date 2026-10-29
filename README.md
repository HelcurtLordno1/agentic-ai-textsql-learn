# Agentic Text-to-SQL — V6

[![CI](https://github.com/HelcurtLordno1/agentic-ai-textsql-learn/actions/workflows/ci.yml/badge.svg)](https://github.com/HelcurtLordno1/agentic-ai-textsql-learn/actions/workflows/ci.yml)

A local Text-to-SQL application for querying SQLite databases in natural language.
V6 includes a command-line interface, FastAPI service, Streamlit workspace, read-only
SQL execution, bounded recovery and monitored local model execution.

The core runs with Ollama and does not require paid provider APIs or API keys.

## What you can do

- Register a local SQLite database and ask analytical questions.
- Inspect generated SQL, result previews and execution status.
- Use the CLI, local API or web interface.
- Keep application history and generated artifacts on your machine.
- Run deterministic checks without downloading datasets or starting a model.

## V6 evaluation snapshot — completed 25 October 2026

| Local evaluation | Result |
| --- | ---: |
| Spider, selected 200-case set | 151/200 — 75.50% |
| Olist, 60-case application set | 54/60 — 90.00% |

Compared with V5, paired gains/losses are **8/0 Spider** and **4/0 Olist**
(+4.00 and +6.67 percentage points). This preserves V5's correct answers on these
manifests; it does not establish general non-regression. P6 remains the default
control and scores higher on the historical Olist set (57/60).

The historical V6 composite contains **240 CPU and 20 GPU predictions**, with
per-case origin preserved. It is neither a uniform GPU run nor a matched speed
comparison. Spider uses the local `spider-release-v2-outer-order` evaluator on
200 cases/20 databases; Olist uses `olist-preview-v2` on 60 reviewed EN/VI cases.
Do not merge their scores or compare this subset directly with official leaderboards.
Execution success is separate from result correctness, and these development-exposed
sets do not establish fresh-test generalization.

## What changed in V6

The measured software variant is **A1 `v5-contracts`**; the report version is V6.
It retains V5 schema-context recovery and derived-column resolution, then adds:

- Bounded question/catalog output contracts for supported projection, scalar AVG
  and grouped-count ranking repairs, followed by revalidation and admission checks.
- Catalog-backed column-owner/PK/FK feedback for operational model repair.
- CPU300 profiles, raw average/instantaneous power telemetry, reviewed subset
  selection and a transport idle timeout of 330 seconds for 300-second HTTP requests.

No fine-tuning, paid API, gold-derived runtime lookup or mandatory LLM planner was added.
Defaults remain P6; V6 is explicitly enabled by [.env.v6.example](.env.v6.example)
or the `v5-contracts` benchmark variant. Generation remains Qwen3-14B Q4_K_M,
context 4096, input/output budgets 2800/768 and at most three generation HTTP attempts.

See the [fresh-clone reproduction guide](docs/v6_reproduction.md) and
[portable configuration recipe](configs/experiments/v6_contracts_cpu300.json).
This release consolidates the completed run's source and transport/monitor fixes;
it does not overwrite historical checkpoints or claim a new benchmark run.

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

For the opt-in V6 application configuration:

```bash
cp .env.v6.example .env
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
Registration and semantic index construction are separate operations. Follow the
[guarded index-building recipe](docs/v6_reproduction.md#4-rebuild-all-21-semantic-indexes-one-guarded-database-at-a-time)
before model requests; the benchmark refuses missing or incompatible indexes.

## Run the local interface

All model requests must run through a monitored launcher. On the approved Windows/WSL
CPU300 configuration, after verifying the 300 MHz hard cap and safe idle, start
the API from the repository root:

```bash
TEXT2SQL_MONITOR_WINDOWS_HOST=true uv run --frozen --extra ui --group dev python -m scripts.run_guarded_local \
  --profile qwen14b-cpu300-stable \
  --stop-file data/artifacts/v6-api.resource-stop.json \
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
predictions, traces, private mentor conversations and secrets are excluded from Git. Keep these local, and use fresh
output paths when changing code, settings or model identities.

## Reproduction boundaries

`make check` verifies the model-free software; reproducing historical accuracy additionally
requires the pinned datasets, model digests, rebuilt indexes and a fresh guarded evaluation.
A seed does not guarantee identical SQL across hardware/backends. The full historical run
had manual pauses, a GPU power stop and a CPU transport incident; those records remain
local and are not relabeled as successful runs. The breached GPU41/batch16 workload
must not be retried through the archived profile. The documented fresh recipe uses CPU0.
No raw historical predictions or checkpoints are distributed with this release.

## License and attribution

Source code is licensed under [MIT](LICENSE). Dependencies, models and datasets retain
their own licenses. Olist data is attributed to Olist; the project's pinned dataset
metadata records CC BY-NC-SA 4.0. Raw Olist data is not redistributed in this repository.
