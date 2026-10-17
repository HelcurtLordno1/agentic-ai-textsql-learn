# Agentic Text-to-SQL

> **V5 research release — 2026-10-17:** A1 `v4-reliability` completed Spider **143/200 (71.50%)** and Olist **50/60 (83.33%)** with the guarded CPU-only profile. Clone `best_research_v5` for this release; `main` publishes the same snapshot. Start with the [V5 reproduction guide](docs/v5_reproduction.md), [machine-readable recipe](configs/experiments/v5_reliability_cpu.json), [aggregate evidence](docs/evidence/v5_benchmark_summary.json), and [Vietnamese report](comparison_new5_to_baseline_vn.md). Historical P6 remains the default/champion; moving this source to `main` does not change pipeline defaults or establish matched-control superiority.

```bash
git clone --branch best_research_v5 https://github.com/HelcurtLordno1/agentic-ai-textsql-learn.git
cd agentic-ai-textsql-learn
make sync
make check
```

The clone contains source, tests, locked dependencies, schema/data contracts, prompts,
guarded benchmark tools and setup examples. Datasets, model weights, databases, indexes,
raw traces/predictions and secrets are rebuilt locally; follow the V5 guide before model work.

[![CI](https://github.com/HelcurtLordno1/agentic-ai-textsql-learn/actions/workflows/ci.yml/badge.svg)](https://github.com/HelcurtLordno1/agentic-ai-textsql-learn/actions/workflows/ci.yml)

A fully local, free, six-layer agentic text-to-SQL learning and portfolio project.
The canonical specification and completion ledger is
[`realistic_project_creation_codex.md`](realistic_project_creation_codex.md).

## Setup and Olist data foundation

```bash
make sync
make check-static
# Full pytest suite, when you want to run tests:
make check
uv run text2sql doctor
uv run text2sql data download olist
uv run text2sql data build olist
uv run text2sql data validate olist
uv run text2sql ingest --db data/processed/olist.sqlite --db-id olist
uv run text2sql serve
# In a second terminal:
uv run streamlit run apps/streamlit_app.py
```

The ordinary CI suite uses fake transports and a deterministic synthetic database; it does not
require Olist, Kaggle, a GPU, or a running model. Olist integration tests run automatically when
`data/processed/olist.sqlite` exists and otherwise skip. `ollama-smoke` is the explicit local model
acceptance test.

The [2026-10-07 corrected commands](docs/run_commands_2026_10_07.md) cover setup, static checks,
tmux pilots, full resume, and attachment. Whole-repository checks explicitly include the `ui`
extra because they inspect API modules; the core installation can still omit this extra.

The Olist build verifies the pinned archive and all CSV hashes/headers/counts, stores money as raw
decimal text plus integer cents, checks integrity/FKs, builds grain-safe semantic views, and only
then atomically publishes SQLite. Raw Olist data and the 175 MiB generated database stay ignored.

## Scope and licensing

Project source code is MIT licensed. Dataset and model licenses are separate. Olist raw files,
generated databases, indexes, and run artifacts are intentionally excluded from Git. See
[`data/README.md`](data/README.md) and [`docs/data/license_and_attribution.md`](docs/data/license_and_attribution.md).

Gate evidence is recorded under [`docs/evidence`](docs/evidence), including the
[`P5 application gate`](docs/evidence/p5_gate.md),
[`P5.1 laptop hardening`](docs/evidence/p5_1_gate.md), and the
[`P6 laptop release`](docs/evidence/p6_gate.md).

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

P6 uses a laptop-stratified Spider-200 release: 100 regression plus 100 disjoint holdout cases over
all 20 databases. It pins every selected row, `dev.json`, `tables.json`, and each SQLite database by
SHA-256. Full Spider-1034 remains a tracked, runnable P6.1 profile for stronger hardware and is not
claimed as completed by the laptop report. Inference checkpoints before any gold-aware evaluation:

```bash
# Future one-case P6 control pilot; not run during A1 construction.
uv run python scripts/serve_ollama_guarded.py --profile acceptance-safe
uv run python scripts/run_guarded_spider.py \
  --profile acceptance-safe --batch-size 1 --cooldown-seconds 60 --max-batches 1 \
  --manifest evals/configs/spider-laptop-200.json \
  --predictions evals/predictions/p6-safe-new-pilot.jsonl \
  --report evals/reports/p6-safe-new-pilot.json
```

Benchmark Lab renders Olist and Spider in separate tabs. Spider reports execution equivalence,
complexity slices, failure taxonomy, latency, manifest identity and explicit limitations; it is not
presented as an official hidden-test leaderboard score.

Verified P6 results on the guarded six-layer laptop profile are Spider-200 130/200 (65.00%;
holdout 67%, regression 63%) and Olist-60 57/60 (95.00%; Vietnamese 96.67%, holdout 100%). Both
workflows completed every case. P95 latency was 85.29 s for Spider and 91.62 s for Olist, above the
60-second interactive target; this limitation is reported rather than hidden. Full Spider-1034 is
still optional P6.1 and has no claimed release score.

## A1 experiment (full V5 run completed)

V5 retains the V4 question-first path and adds opt-in recovery for empty selected relations
and lexical-scope resolution for derived outputs. The measured variant is `v4-reliability`;
the historical experiment prefix is retained in the report for provenance. Its approved
profile is `qwen14b-cpu600-stable`: generation GPU offload0, CPU8, internal batch64,
FA off/f16 KV, context4096, input2800/output768, maximum3 requests, case900s/request300s.
Benchmark batch1, unload/cooldown60s and continuous Windows/WSL resource monitoring remain
mandatory. Use [V5 setup and guarded commands](docs/v5_reproduction.md) for a fresh run.
The paragraphs about V4 below retain the preceding experiment's historical configuration.

`TEXT2SQL_PIPELINE_MODE=a1` selects question-first generation without an LLM planner.
Catalog evidence includes PK/FK/uniqueness; CPU clause checks expose contradictions or UNKNOWN.
`TEXT2SQL_CRITIC_MODE=shadow` collects a bounded local critique without changing the draft.
`repair` additionally requires correction enabled and admits at most one candidate only when
grounded contradictions improve and untargeted SQL structure remains unchanged.
Recoverable syntax/column/function errors have a separate one-repair route; policy violations
and timeouts do not. Risk routing and a fixed shadow sample are configurable; LLM findings
stay advisory. Typed traces preserve every evaluated draft/repair and the selection reason.
A shared three-attempt budget includes malformed JSON retries. `TEXT2SQL_GENERATION_FORMAT=sql_text`
prepares a native SQL output route for a digest-pinned specialist; model/template pilot is pending.

All model calls require a monitored wrapper, explicit offload and unload. Current suite limits
are RAM ≥14 GiB, swap <0.25 GiB, VRAM <6 GiB, GPU <68 C and <70 W, one case per batch,
0.5-second sampling and 60-second cooldown. Generated audits/checkpoints stay ignored.
P6 scores above are historical; they do not measure A1 or the current safety profile.
The completed V4 run used the explicitly authorized full-GPU 450 MHz profile with
41 GPU layers, RAM ≥8 GiB, VRAM <14 GiB, swap <0.25 GiB, temperature <68 C,
power <70 W, batch 1, unload and cooldown 60 seconds. The defaults above remain
conservative for other workloads. Follow the [V4 reproduction guide](docs/v4_reproduction.md)
for the completed source and new-run commands; older dated handoffs retain their history.

The [novelty assessment](docs/research_plan/novelty_and_repairability_2026_10_03.md) narrows the
research question to repairability-based compute allocation and constrained AST edits.
`TEXT2SQL_COMPUTE_POLICY=obligation` enables edit contracts; optional CPU ranking repair keeps
the rest of the SQL unchanged. Metric binding is currently lexical and deliberately narrow.
`TEXT2SQL_REPAIRABILITY_ROUTING=false` retains risk routing with the same contracts for ablation.
The V4 run recorded zero eligible semantic contracts, zero CPU repairs and zero critic
calls. Spider accuracy improved relative to historical P6 while Olist regressed; the
different compute profiles prevent attributing the observed latency change to architecture.

`scripts/tmux_experiment.py` provides `run`, `pause`, `resume`, `attach`, and `status` with frozen
plans and persistent logs. Detach keeps the guarded workload running; pause waits for a case
checkpoint and cooldown. Completion prints `SUCCESS FINISH ALL` after report validation;
resource latches and source/config identity checks still refuse unsafe or mixed resumes.
See the [Administrator cap and full run/resume commands](docs/a1_run_after_coding.md#6-nvidia-administrator-giới-hạn-graphics-clock-300800-mhz).
