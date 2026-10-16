# R2 RTX A4500 architecture and benchmark plan

**Date:** 2026-09-12 (Asia/Bangkok)

**Gate:** one systemic optimization revision, then one source-locked Olist evaluation

**Outcome:** architecture/runtime construction passed, but the source-locked evaluation stopped at
`16/20`; upper bound `56/60` is below the `57/60` promotion threshold. Candidate rejected; see
`comparison_new2_to_baseline_vn.md`.

## Objective and falsifiable criteria

The candidate must run safely on the RTX A4500 Laptop GPU and preserve or improve the frozen P6
Olist champion. Construction and benchmark are separate gates:

1. `make check` passes with deterministic distribution, dependency, and orchestration tests.
2. A new one-case guarded pilot produces executable SQL before the bounded request timeout.
3. The pilot remains below 14 GiB minimum available RAM, 0.25 GiB swap, 4 GiB VRAM, 65 C, 70 W,
   and 650 MHz while an Administrator 300–600 MHz clock lock is active.
4. Only after the pilot passes may its exact checkpoint continue to Olist-60.
5. Promotion requires at least the frozen `57/60`; the research target is at least `58/60`.
6. The existing upper-bound kill criterion stops the run as soon as `57/60` becomes impossible.

No benchmark ID, gold SQL, expected result, or observed failure is available to runtime code.
Spider remains blocked until Olist non-regression passes.

## Root-cause model

The adaptive revision `e8fab80` restored P6 behavior but retained a cost-unbounded control path:

```text
planner LLM -> adaptive route -> embedding model -> generator LLM -> optional corrector LLM
```

This has four architecture-level costs on a one-model local runtime:

- EASY pays for an LLM planner before the system knows DIN is unnecessary;
- routing depends on that expensive planner even though its signals are structurally derivable;
- hybrid query retrieval loads BGE between Qwen planning and generation;
- `keep_alive=0` permits repeated Qwen reloads inside one case even though the wrapper already
  guarantees unload after each checkpoint.

The 600-second pilot timeout happened in the first planner call, before adaptive routing or SQL. It
is therefore not evidence about Paper II accuracy and must not trigger a case-specific repair.

## Construction

### 1. Deterministic control plane

Build a typed `LogicalPlan` skeleton directly from `DecomposedQuestion`, then apply the same global
alignment invariants used after model planning. Hybrid routing consumes this skeleton before any
LLM call. Baseline mode remains available as the frozen ablation.

Expected LLM-call budget:

| Route | Before | After |
|---|---:|---:|
| EASY / baseline-preserve | 2 plus correction | 1 plus correction |
| explicit complex DIN | 3 plus correction | 2 plus correction |

### 2. One grounding pass

Hybrid runs prepare semantic links and bounded schema context once after routing. Baseline-preserve
uses the context but not the semantic compiler. Complex DIN reuses the same evidence for its typed
planner; it does not retrieve twice.

### 3. Laptop retrieval policy

The A4500 benchmark profile uses the already-built BM25 index at query time. It must not instantiate
or call the BGE runtime client. This prevents generation and embedding model overlap/model eviction,
while index identity and catalog checks remain enforced. Hybrid retrieval remains a reproducible
ablation for server or interactive profiles.

### 4. Per-case model residency and bounded time

Keep Qwen resident only within a case so planning, generation, and correction reuse one load. The
guarded wrapper still unloads all models after every one-case batch and applies a 60-second cooldown.
Typed profile fields define request timeout, run deadline, and output-token cap instead of hidden
script overrides.

The pinned Qwen manifest and its five content-addressed blobs are staged on native ext4 and each
blob SHA-256 is verified before use. This removes repeated NTFS/WSL model-load latency without
changing model bytes, digest, prompt, GPU offload, or accuracy semantics.

### 5. Calibrated A4500 profile

Start with six GPU layers—the previously measured P6 offload—under a verified 300–600 MHz hard
clock lock. Use one model, one request at a time, 10 CPU cores, q8 KV, 512 output tokens, 240-second
request timeout, and 180-second correction deadline. The safety stops are not loosened: VRAM 4 GiB,
65 C, 70 W, clock watchdog 650 MHz, minimum 14 GiB available RAM, and swap below 0.25 GiB.

### 6. Linear-time evaluator and safe interruption

The guarded wrapper keeps evaluator-only expected rows in memory so each newly exposed gold query
executes once, rather than recomputing the entire prefix after every checkpoint. Runtime remains a
separate gold-blind subprocess. The final report still evaluates the complete manifest. A keyboard
interrupt during monitoring must stop the child process group and unload models before returning;
it cannot leave inference outside the guard.

## Verification matrix

- deterministic planner preserves scalar/grouped/ranking/set constraints in both languages;
- adaptive route is selected before provider invocation;
- EASY hybrid uses exactly one model call and baseline generator;
- complex hybrid uses exactly two model calls and DIN generator;
- grounding is performed exactly once per query;
- BM25 profile cannot invoke the embedding callback;
- profile environment explicitly bounds GPU layers, tokens, deadlines, concurrency, and residency;
- guards reject every threshold boundary and unload after each batch;
- repeated prefix scoring reuses an explicit evaluator-only cache;
- guarded interruption stops the child group before exiting;
- runtime/evaluator dependency separation remains intact.

## Benchmark protocol

1. Pass `make check`, commit, and record the clean source revision.
2. Confirm no stale model/benchmark process and sample idle RAM/swap/VRAM/temp/power/clock.
3. Apply and verify the Administrator 300–600 MHz graphics-clock lock.
4. Start guarded Ollama with `olist-paper2-a4500-safe`; sample every 0.5 seconds.
5. Start a fresh one-case Olist artifact in hybrid mode with minimum-correct 57.
6. Continue that exact checkpoint only if it emits SQL within 240 seconds and all peaks pass.
7. Continue batch size one, unload, 60-second cooldown, continuous dual monitoring, and offline
   scoring. Never retry a resource breach.
8. Stop on the accuracy upper-bound criterion; otherwise finish all 60 and write the report.
9. Stop/unload Ollama, reset the hard clock, verify idle state, rerun `make check`, and update the
   canonical ledger without changing the measured score.

## Recorded outcome and causal limitation

Steps 1–9 were followed for evaluation `olist-paper2-a4500-c40b75c-v1`. The pilot succeeded, the
same checkpoint continued, and accuracy exit 76 stopped the run at 20 cases with `16/20` correct
and a maximum possible `56/60`. No resource guard was breached; Ollama was unloaded, the clock cap
was reset, and idle resources were verified.

The planned treatment did not isolate DIN planning: it replaced the frozen P6 planner LLM with a
deterministic control skeleton and its laptop retrieval policy replaced hybrid retrieval with BM25.
Nineteen of 20 cases took `BASELINE_PRESERVE`; all three paired regressions were in that route,
while the single DIN-enhanced case was correct. A future gate must hold the P6 planner and
retrieval/context constant and change one intervention at a time. It may not reuse this checkpoint
or infer a general DIN-SQL effect from one complex-route observation.

## Revision B: baseline-equivalent control (2026-09-12)

Revision B removes both confounds. Hybrid mode first runs the frozen planner v2. Preserve cases then
use the normal `ground()` and baseline generator/corrector; only DIN-routed cases call decomposed
grounding and planner v3. Integration tests assert the preserve call sequence and the bounded extra
calls on a complex route. `make check` passed 240 non-Ollama tests.

Administrator hard-capped the GPU at 300--600 MHz. A new one-case pilot passed, and the exact same
checkpoint continued under `olist-paper1-ultrasafe`. Accuracy exit 76 stopped it at 14 cases with
`10/14` correct: its maximum possible full-suite score was `56/60`, below the frozen `57/60` gate.
P6 was `13/14` on the same prefix. The only DIN-routed case was correct; three new paired failures
were preserve cases, so one complex observation cannot identify a DIN effect and ordinary model
variance remains a plausible contributor.

No resource breaker fired. Continuous monitoring observed peak VRAM 1,719 MiB, 57 C, 72.26 W,
98% utilization and 600 MHz; minimum available RAM was 22.31 GiB and swap use was zero. Ollama and
benchmark processes were removed after the accuracy stop. Revision B is rejected for promotion,
must not resume this checkpoint, and Spider remains blocked. The next revision must use a separate
development partition to quantify control variance and isolate exactly one of proof-graph
validation or join-hop-aware decomposition before another source-locked Olist run.

## Revision C: semantic proof and bounded hierarchical backtracking (2026-09-13)

Revision C is a new construction gate informed by SQLens, DAC, multi-grained error identification,
and DART-SQL. It adds gold-blind question/entity/skeleton checks for explicit values and identity,
scalar group-filter grain, distributions, and tie breaks. Semantic checks inspect original SQL while
the executor retains its normalized safety limit. Correction may make two clause-local attempts,
stops on repeated SQL/error, and expands schema only for owner/join evidence when the whole catalog
is at most 12 tables and 1,600 estimated tokens.

The reused four-case failure diagnostic is not promotion evidence. It recovered cases 003 and 007
from incorrect first passes. Case 014 exposed and motivated the safety-limit separation. Case 011
showed that even two corrections and bounded full-catalog expansion preserve the wrong baseline
skeleton; therefore returning-customer with a more-than-one-order predicate is now classified as a
group-filter aggregate dependency and routed to DIN semantic planning. A fresh construction check
and clean evaluation are required; R2 remains `IN_PROGRESS` and Spider remains blocked.
