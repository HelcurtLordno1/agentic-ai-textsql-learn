# Gate P5.1 evidence — 2026-08-13

## Scope and decision boundary

P5.1 hardens the verified P5 application before P6. It is not a paper-benchmark claim and it does
not reuse the previously inspected Olist holdout as a fresh holdout. Development was restricted to
the 11 known P5 failures in the dev/regression partitions; the two old holdout failures remain
sealed from live tuning. Full cross-domain and fresh-holdout evaluation remains P6.

## Reliability changes

- Planner v2 deterministically preserves bilingual scalar/ranking intent, exact requested limit,
  descending primary metric and ascending tie-break; returning-customer questions normalize to one
  output metric.
- Generator v3 requires displayed column ownership and discourages unused joins/CTEs.
- The semantic gate adds high-precision, gold-independent rules for ranking, overall averages,
  customer identity/output shape, late-delivery population, scalar maximum, row-count semantics,
  order-grain freight, duplicate reviews, product photos and year-month grouping.
- Shape failures retain semantic signals so one bounded repair receives the actual root-cause
  guidance. The request deadline is 120 seconds, but repair count and LLM call count remain one.
- Ollama responses expose per-query load, prompt-evaluation, decode, token and embedding telemetry;
  RuntimeBundle records deltas rather than cumulative process totals.

Frozen replay against the ignored P5 prediction artifact flagged all 13 historical wrong SQL
outputs and zero of the 47 historical correct SQL outputs. This is detection evidence only, not a
new 60-case accuracy result.

## Laptop governor and rejected optimization

Typed profiles now drive the Ollama environment and acceptance runner. The production laptop
profile uses 8 Qwen GPU layers, 12 low-priority logical CPU cores, one parallel request, context
4096, Flash Attention, q8_0 KV cache, BGE query embedding on CPU, and at most two loaded models.
The independent supervisor samples every 0.5 seconds and stops the Ollama process group at:

- available RAM below 10 GiB;
- swap at or above 1 GiB;
- VRAM at or above 11,776 MiB;
- GPU temperature at or above 76 C;
- GPU power at or above 105 W (reported 100 W hardware max plus 5% instantaneous margin);
- or any monitor failure.

Short 12- and 14-layer experiments looked safe in occasional snapshots and were 10–18% faster,
but the independent monitor captured transient 108.02 W and 137.65 W peaks and stopped both. They
were rejected. A two-case 10-layer pilot completed 2/2 correctly with one successful repair, P50
54.74 s and P95 81.08 s. Its observed peak was 3,728 MiB VRAM, 61 C, 81.86 W, zero swap, and at
least 22.39 GiB available RAM, but a longer pilot later reached 101.93 W; 10 layers was therefore
also rejected. An 8-layer pilot briefly read 99.53 W, inside the device's reported 100 W hardware
maximum once measurement granularity is considered. The final 105 W stop does not alter the GPU's
80 W default/85 W current power limit. Production evidence below uses 8 layers.

## Dev/regression failure ablation

The final homogeneous 8-layer dev/regression run completed 11/11 typed terminals and scored 10/11
(90.91%), with 5/6 bounded corrections recovered (83.33%). P50 was 78.45 s and P95 was 111.75 s;
this is slower than P5 because stability was explicitly prioritized. The only rejected case was a
scalar maximum whose generated SQL was already the correct `MAX(...)`, but its old plan retained a
ranking `LIMIT 1` and the validator self-rejected it. Planner alignment was fixed to clear ranking
shape for scalar maximum, unit-tested, then the exact case passed 1/1 first-pass in 49.00 s under
the same 8-layer profile. Therefore final-code coverage is 11/11 across the frozen dev/regression
failure cohort, while the immutable homogeneous report remains honestly reported as 10/11.

The 11-case supervisor observed at least 22.42 GiB available RAM, zero swap, 3,307 MiB VRAM, 62 C,
89.08 W and 97% GPU utilization without a breach. The final scalar rerun observed 3,309 MiB VRAM,
60 C and 93.01 W. Accuracy improved through explicit semantic contracts and correction—not through
gold data in runtime. Final repository-wide `make check` passed: Ruff lint, format verification of
186 files, strict mypy over 101 source files, and 158/158 non-live tests (one explicit Ollama test
deselected). The only warning is the existing upstream Starlette TestClient deprecation.

Gate result: `GATE_P5_1_VERIFIED`.
