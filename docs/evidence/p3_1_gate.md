# Gate P3.1 evidence — 2026-08-09

## Why this hardening gate exists

A post-P3 audit found four benchmark defects: the nominal mini-100 contained 99 unique cases,
column recall matched unqualified names across tables, FK recall assigned 1.0 to no-join cases, and
reported retrieval latency excluded query embedding. The schema linker also ignored its
`LogicalPlan`, P2 generation bypassed Layer 2, hybrid weight 0.01 was effectively dense-only, and
index publication deleted the previous bundle before rename. P3.1 corrects these defects; P3
reports remain historical and are superseded by this document.

## Hardened architecture

- BGE-M3 tag and digest are pinned; current digest is
  `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`.
- Indexes are immutable `versions/<version_id>` bundles with atomically replaced `active.json`.
- Manifest validates catalog/template/model identity, 1,024-vector dimension, document count and
  every artifact SHA-256. BM25 is JSON, not executable pickle.
- SQLite embedding cache is transactional. A failed rebuild leaves the previous active bundle
  loadable; fixed build locks reject concurrent writers.
- Schema linker uses plan terms, adds relationship endpoints/join columns, computes a minimal FK
  closure bounded to two hops, renders the exact final schema string and enforces its token budget.
- Generator prompt v2 accepts either full catalog or typed grounded context; every prediction
  records schema evidence, final context and prompt token estimate.

Twenty Spider domains were rebuilt/reloaded. Document embedding cold-build time across their
immutable manifests totals 128.64 s; median database build 4.91 s, max 15.49 s. Checksum reload
median is 83.36 ms, p95 95.91 ms. Query embedding is reported separately: recorded unique-request
p50 4.461 s, p95 5.027 s, first recorded request 8.186 s. Warm ranking + linking p95 remains below
3 ms. This ~5 s cost is included in grounded end-to-end latency, not hidden.

## Benchmark integrity

`spider-mini-100.json` contains exactly 100 unique pinned dev indices and case hashes across all 20
dev domains. Because implementation was inspected against this set during hardening, it is labeled
regression/tuning data. A second `spider-holdout-100.json` was generated from disjoint dev rows,
overlap 0, and evaluated once only after code/fusion freeze; it covers 19 domains because the sole
four-row domain was exhausted by the domain-balanced mini manifest.

Gold extraction uses SQLGlot qualification with the real catalog and case-insensitive SQLite
identifiers. Columns are `table.column`; derived scopes and aliases are resolved. Declared FK recall
is distinct from general join-edge recall. No-column/no-FK cases are excluded from the respective
macro denominator. Reports contain macro/micro metrics at k=5/10/20.

## Qualified retrieval results at k=20 after schema linking

Spider regression mini-100:

| Mode | Table macro | Column macro | Schema macro | FK conditional | Join conditional | Avg context tokens |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 0.9950 | 0.9446 | 0.9586 | 0.9118 | 0.8611 | 117.55 |
| Dense | 1.0000 | 0.9926 | 0.9948 | 0.9412 | 0.8889 | 142.20 |
| Hybrid | 1.0000 | 0.9978 | 0.9981 | 0.9412 | 0.8889 | 145.13 |

Disjoint untouched holdout-100:

| Mode | Table macro | Column macro | Schema macro | FK conditional | Join conditional | Avg context tokens |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 0.9800 | 0.9225 | 0.9379 | 0.8281 | 0.8030 | 102.03 |
| Dense | 1.0000 | 0.9939 | 0.9963 | 0.8906 | 0.8636 | 137.61 |
| Hybrid | 1.0000 | 0.9965 | 0.9975 | 0.8906 | 0.8636 | 138.01 |

Equal-weight RRF hybrid is retained because it beats dense qualified column/schema recall on the
disjoint holdout without table/FK regression. The former 0.01 BM25 weight is removed.

Olist reports physical-only and semantic catalogs separately. Semantic hybrid@20 reaches table
macro 0.9815, qualified column macro 0.8922 and schema macro 0.9364 at 246.5 context tokens. Raw
physical retrieval cannot retrieve gold semantic views and is reported separately rather than
mislabeling a mixed catalog as raw.

## Grounded generation ablation

Both variants used Qwen3 `qwen3:14b-q4_K_M`, prompt `generator_v2_grounded`, the same 20 Olist smoke
cases and no correction/gold feedback.

| Variant | Result accuracy | Typed terminal | Avg prompt tokens | p95 total latency |
|---|---:|---:|---:|---:|
| Full schema | 14/18 (77.78%) | 20/20 | 2,116.00 | 32.12 s |
| Semantic hybrid grounded | 14/18 (77.78%) | 20/20 | 1,228.06 | 46.40 s |

Grounding is accuracy-neutral on this small set and reduces estimated prompt tokens by 41.96%.
It adds about 5–6 s per unique query embedding and the measured p95 increases 14.29 s, while
remaining below the 60 s run deadline. The same four cases remain result-incorrect; grounding is
not claimed as an accuracy improvement. One previously policy-blocked case now executes but remains
semantically wrong. These failures remain inputs to P4, not reasons to alter P3.1 gold or metrics.

## Verification

Focused hardening tests cover stable build/reload, checksum corruption, cross-db rejection, final
budget, failed-build rollback, plan-sensitive selection, qualified same-name columns, 100 unique
manifest rows, stable RRF and Ollama model digest. Final `make check` output is recorded after the
canonical docs update: Ruff lint pass, Ruff format 162 files pass, strict mypy 95 source files pass,
and pytest excluding the explicit live-model marker reports 126 passed and 1 deselected. Gate P3.1
is `HARDENED_VERIFIED`; correction P4 has not started.
