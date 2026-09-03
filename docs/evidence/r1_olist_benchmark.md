# Paper I / PRACTIQ Olist benchmark evidence

Status: `IN_PROGRESS — HARDWARE_CAP_REQUIRED`
Date: 2026-09-01 (Asia/Bangkok)

## Research question

Does the PRACTIQ-inspired pre-SQL reliability gate improve the reviewed Olist-60 application result
accuracy over the frozen P6 Qwen3-14B baseline without using gold evidence at runtime?

The frozen baseline is `evals/reports/olist-p6-60.json`: 57/60 result-correct (95.00%), 60/60 typed
terminal, with three public development/regression failures (`olist_acc_014`, `olist_acc_023`, and
`olist_acc_038`). The 15-case holdout was already 15/15 and was not used for code changes.

## Development regression fixes

All three prior failures were rerun independently using Qwen3 `qwen3:14b-q4_K_M`, seed 42, the new
question-reliability gate, glossary-grounded interpretations, and the same reviewed gold evaluator:

| Case | Previous failure | New result |
|---|---|---:|
| `olist_acc_014` | Full status distribution incorrectly limited to one row | 1/1 correct |
| `olist_acc_023` | Customer state confused with customer identity | 1/1 correct |
| `olist_acc_038` | Delivered-status predicate omitted | 1/1 correct |

The fixes are general constraints rather than gold SQL: distinguish sorted distributions from top-k,
preserve accepted interpretation concepts through scalar planning, prefer a base entity relation for
an unqualified entity count, and preserve explicit status plus non-null timestamp conditions.

## Locked Olist-60 v1 attempt

The run pinned the manifest, model digest
`bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`, seed 42, prompt versions,
glossary, and source hashes in
`evals/predictions/olist-paper1-r1-60-v1.provenance.json`. Runtime had no access to gold SQL or result
hashes. It used one case per process, one GPU layer, one loaded model, 0.5-second monitoring, unload
between cases, and 60-second cooldown.

The resource circuit breaker stopped v1 at 5/60 when GPU power reached 78.68 W. Peak GPU temperature
was 64 C, VRAM 1,922 MiB, additional RAM use about 0.96 GiB, available RAM at least 22.25 GiB, and
swap zero. Both the benchmark process group and guarded Ollama server stopped; no automatic retry was
made.

The persisted prefix was evaluated separately and honestly:

| Metric | Prefix result |
|---|---:|
| Typed terminal / valid candidate | 5/5 / 5/5 |
| Result accuracy | 4/5 (80.00%) |
| First-pass correct | 4/5 (80.00%) |
| P50 / P95 latency | 57.21 s / 138.39 s |

The one wrong prefix case was the generic total-order count: retrieval selected the child payment
fact instead of the base order entity. This is a real regression relative to P6. The entity-owner
grounding fix was added afterward and covered by deterministic tests, so the v1 checkpoint cannot be
resumed or combined with the changed source snapshot.

## Claim boundary and next run

No full-suite accuracy improvement is claimed. The 3/3 development regression result and 4/5 v1
prefix are diagnostic, not a replacement for Olist-60. A clean `olist-paper1-r1-60-v2` must run from
case 1 after a verified hardware-level GPU clock/power cap prevents repeated operation at 78 W. The
release criterion remains at least 58/60 and no holdout regression; the evaluator result will be
reported even if it fails that criterion.

Latest repository verification after the hardware-policy hardening on 2026-09-03: Ruff pass, format
pass, strict mypy pass for 110 source files, and 217 non-Ollama tests passed with one Ollama-marked
test deselected. No local model or benchmark was started for this verification.
