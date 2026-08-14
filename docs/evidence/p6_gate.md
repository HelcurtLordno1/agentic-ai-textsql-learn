# Gate P6 evidence — 2026-08-14

## Decision

Gate P6 is `VERIFIED` for the reproducible local release profile. The release combines a guarded,
laptop-stratified Spider-200 generalization benchmark with a fresh Olist-60 application acceptance
run. Scores remain separate. Full Spider-1034 is optional P6.1 and is not claimed complete.

## Spider-200 generalization

The tracked manifest pins 200 selected Spider-dev rows, source metadata, and 20 SQLite databases by
SHA-256. It contains regression-100 plus a disjoint holdout-100, grouped by database only to reuse
catalog/index work. Inference used Qwen3-14B Q4_K_M, BGE-M3 hybrid retrieval, seed 42, six GPU
layers, bounded correction, and pinned model digests. Gold was opened only after all predictions
were checkpointed. The evaluator exact-gold self-test passed 1,034/1,034 cases.

| Metric | Result |
|---|---:|
| Typed workflow completion | 200/200 (100%) |
| Valid candidate | 199/200 (99.50%) |
| Execution accuracy | 130/200 (65.00%) |
| Regression | 63/100 (63.00%) |
| Holdout | 67/100 (67.00%) |
| Easy | 83/107 (77.57%) |
| Medium | 27/53 (50.94%) |
| Hard | 16/29 (55.17%) |
| Extra-hard | 4/11 (36.36%) |
| P50 / P95 latency | 58.51 s / 85.29 s |

All 70 failures remain in the denominator: 68 `EXECUTION_MISMATCH`, one
`UNKNOWN_RUNTIME_ERROR`, and one safely `WRITE_BLOCKED`. The report records database and complexity
slices, manifest identity, runtime/index provenance, artifact hashes, and limitations. This is not
an official hidden Spider leaderboard score.

## Olist-60 application fitness

The same code revision reran the reviewed bilingual acceptance manifest from clean predictions.

| Metric | Result |
|---|---:|
| Typed workflow completion / valid candidate | 60/60 / 60/60 |
| Result accuracy | 57/60 (95.00%) |
| First-pass correct | 51/60 (85.00%) |
| Dev / regression / holdout | 28/30 / 14/15 / 15/15 |
| English / Vietnamese | 28/30 / 29/30 |
| Correction attempted / recovered | 6 / 6 |
| P50 / P95 latency | 61.92 s / 91.62 s |

Accuracy, correction recovery, and holdout exceed the application threshold. P95 latency remains
above the 60-second interactive target and is an explicit limitation; Gate P6 is an engineering and
evaluation completion claim, not a claim that every stretch target is met.

## Laptop safety and reproducibility

Spider ran in resumable batches with cooldown and an independent fail-closed Ollama supervisor.
Two isolated power-sensor breaches caused immediate model shutdown at durable checkpoints; resume
preserved the same commit, seed, model digests, index identities, and six-layer configuration. Safe
segments stayed at 60–61 C, about 2.7 GiB VRAM, zero swap, and at least 18.86 GiB available RAM.
The Olist run peaked at 91.75 W, 61 C, 2,725 MiB VRAM, 3.82 GiB system RAM used, and zero swap.

Raw predictions, gold, databases, indexes, and reports remain ignored. The tracked demo artifact is
sanitized and contains no per-case details. The final repository verification and CI result are
recorded in the completion commit and GitHub Actions run.

Gate result: `GATE_P6_VERIFIED`.
