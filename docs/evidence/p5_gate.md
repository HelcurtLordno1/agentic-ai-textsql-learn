# Gate P5 evidence — 2026-08-13

## Decision

Gate P5 is `VERIFIED` for the local Layer 6 application boundary. The gate proves a complete
CLI/API/UI path, persistent six-layer audit history, a reviewed Olist-60 acceptance set, and an
engaging read-only UI. It does not claim portfolio-complete cross-domain accuracy; that remains P6.

## Application architecture

- One `ApplicationQueryService` is shared by CLI and FastAPI; Streamlit calls FastAPI only.
- The SQLite application store persists registered catalog snapshots, immutable run config,
  results, layer 0–6 events, and categorized local feedback with WAL enabled.
- Stored config includes generation/embedding model identity, model digests, catalog/index version,
  Ollama options, correction flag, deadlines, row caps, and executor timeout.
- API query execution is bounded to one worker. SSE replays persisted events after reconnect; a
  non-blocking trace endpoint supports active-run inspection. Restart recovery converts orphaned
  queued/running work to a typed failed terminal while completed runs remain replayable.
- Requests accept registered `db_id` values only. The browser cannot supply filesystem paths,
  execute edited SQL, or bypass Layer 4 policy/read-only execution.

## Local SQL Observatory

The Streamlit application has five workspaces: Query Studio, Run Inspector, History, Benchmark
Lab, and System Center. It includes bilingual question starters with smooth drag reordering,
keyboard select fallback, a drag-resizable sidebar, responsive navy/violet/cyan visual tokens,
deterministic KPI/table/chart presentation, plan/schema/SQL evidence, trace download, persisted
history, opt-in bounded correction, and categorized correct/incorrect feedback.

Streamlit's `AppTest` rendered the application with no exception and observed all five navigation
targets plus Database and starter selectors. A live headless server returned `ok` from
`/_stcore/health`; the FastAPI health route and Olist registry reported one 17-object catalog.

## Reviewed Olist-60 acceptance

`evals/configs/olist-acceptance-60.jsonl` contains exactly 60 manually specified, unique bilingual
questions and 60 unique gold queries: 30 dev, 15 regression, and 15 holdout; 30 English and 30
Vietnamese. Loader invariants reject duplicate IDs, questions, gold SQL, incorrect partitions, or
unreviewed cases. All gold SQL executed successfully against a read-only staged Olist database.

Inference received only question, database, and catalog. It checkpointed each prediction before the
model runtime closed; the evaluator then opened gold SQL and compared result rows with declared
ordering and numeric tolerance. Full predictions/details remain ignored.

| Metric | Result |
|---|---:|
| Typed workflow completion | 60/60 (100%) |
| Valid candidate generated | 60/60 (100%) |
| Result accuracy | 47/60 (78.33%) |
| First-pass correct | 43/60 (71.67%) |
| Dev | 24/30 (80.00%) |
| Regression | 10/15 (66.67%) |
| Holdout | 13/15 (86.67%) |
| English | 24/30 (80.00%) |
| Vietnamese | 23/30 (76.67%) |
| Easy | 32/37 (86.49%) |
| Medium | 14/21 (66.67%) |
| Hard | 1/2 (50.00%) |
| P50 latency | 42.06 s |
| P95 latency | 82.35 s |
| Correction attempted / recovered | 6 / 4 |

There are 13 failed result cases: 11 reached `SUCCEEDED` but produced wrong rows and two were
caught as `RESULT_SHAPE_MISMATCH`. Dominant visible errors include incorrect ranking/order,
incorrect population/filter, wrong aggregation grain, and extra output shape. No failed case is
removed from the score.

P95 is above the 60-second target and is not hidden. The acceptance run spans the same model/prompt/
index contracts but two hardware profiles because the original full-GPU run overloaded the laptop.
It is valid accuracy evidence, but not a clean latency comparison. A homogeneous performance rerun
is deferred; it is not required to prove the P5 application gate.

## Laptop resource hardening

The original continuous full-GPU acceptance twice destabilized the host. The replacement guarded
runner is checkpointed and fail-closed:

- one case per batch, model unload, and 20-second cooldown;
- Ollama parallelism/model count bounded to one and context fixed at 4096;
- Qwen partial offload of 12 GPU layers and Ollama restricted to 12 logical CPUs at low priority;
- two-second independent monitoring of RAM, swap, VRAM, GPU temperature, and power;
- automatic interrupt while preserving checkpoint at RAM available <10 GiB, swap used >=1 GiB,
  VRAM >=11.5 GiB, GPU >=76 C, or power >=95 W.

The guard stopped an unsafe pilot at 139.12 W before advancing its checkpoint. The final balanced
segment completed with observed peak 2.08 GiB system RAM used, zero swap, 4,308 MiB VRAM, 60 C, and
76.54 W. Resource-guard threshold behavior is covered by deterministic tests. Ollama documents
that memory scales with parallelism multiplied by context and supports explicit model unload;
NVIDIA documents temperature, power, memory, and utilization telemetry through `nvidia-smi`.

## Reproducible verification

Focused P5 suites cover run/config/trace persistence, restart recovery, catalog path constraints,
feedback validation, shared service run IDs, API asynchronous/SSE/replay/restart behavior, CLI
persistence, UI dependency boundaries, Olist manifest/evaluator behavior, and all resource guard
thresholds. Final repository-wide `make check` passed: Ruff lint, 182-file format check, strict mypy
over 100 source modules, and 149/149 non-live tests (one explicit Ollama test deselected). The only
warning is an upstream Starlette deprecation emitted from `fastapi.testclient`; no application test
failed. Final headless rehearsal returned `ok` for Streamlit health, and AppTest rendered all five
workspaces with zero exceptions.

Gate result: `GATE_P5_VERIFIED`.
