# Post-P6 schema and interactive-runtime hardening — 2026-08-16

## Incident and root cause

The UI question `Top 5 danh mục theo doanh thu sản phẩm, tách phí vận chuyển, giải thích` ended as
`POLICY_BLOCKED` with `Unknown column: order_item_totals.product_id` after 26.43 seconds. The same
failure reproduced without the appended word `giải thích`, ruling out that suffix as the trigger.
Trace `f5185b7b-a5e9-4f3c-b82b-38c4fe1e240c` showed a mixed schema context: the connected raw
`olist_order_items_dataset` / `olist_products_dataset` pair plus disconnected aggregate view
`order_item_totals`. The model invented a key absent from that view. Policy detection was correct,
but the application mislabeled this schema-invalid SQL as a policy block.

## Changes

- FK closure evaluates every retrieved seed as an anchor and deterministically selects the smallest
  connected component covering the most retrieved evidence. Disconnected decoys are excluded even
  when ranked first.
- Generator v5 and corrector v4 require exact column ownership and declared FK joins. An aggregate
  view lacking a required dimension/path must be replaced by a connected raw metric source.
- Schema/syntax/dialect failures now return `INVALID_SQL`; only actual safety violations return
  `POLICY_BLOCKED`.
- Registered databases are copied atomically to a read-only WSL-native temp cache before execution.
  Cache publication is concurrency-safe and rejects a source that changes during staging. All
  existing read-only SQLite defenses and resource bounds still apply.
- Streamlit reuses one HTTP client, caches small metadata with TTLs, lists result-free run summaries,
  lazy-loads heavy UI dependencies, and polls active inference in a fragment instead of blocking the
  whole page. Drag sorting remains available as an opt-in enhancement with an immediate keyboard
  fallback. Streamlit file watching is disabled because WSL poll-based watching was observed to
  accept TCP connections while starving HTTP responses; with watching disabled, health returned in
  0.001 seconds and the root document in 0.012 seconds.

## Reproducible evidence

Focused regression suites passed 28/28. Repository gate command `make check` passed:

- Ruff lint: passed;
- Ruff format check: 199 files formatted;
- mypy: 105 source files, zero issues;
- pytest excluding the explicit Ollama test: 172 passed, one deselected.

Live retest run `3e49bb05-a05c-4722-bb82-ecd238f04bd6` used the exact incident question against the
final rank-independent closure and completed
`SUCCEEDED`. Its context contained only the two connected raw tables and their declared
`product_id` FK. SQL grouped product categories and returned separate revenue and freight columns;
SQLite execution itself took 0.229 seconds from the staged cache and end-to-end pipeline latency was
96.90 seconds. A controlled comparison of the
same query took 30.774 seconds on `/mnt/d` and 0.192 seconds on `/tmp`, approximately 160x faster for
that execution path. Planner and generator inference dominate the remaining latency, not SQLite or
API transport.

HTTP measurements after summary projection were 0.012 seconds for health, 0.045 seconds for
catalogs, and 0.022 seconds for run-history summaries. Streamlit AppTest initial render decreased
from 24.22 to 14.62 seconds. After the first render, History took 0.057 seconds, Benchmark Lab 0.162
seconds, System Center 0.081 seconds, and return to Query Studio 0.038 seconds; Run Inspector's first
result render took 4.94 seconds. All five workspaces had zero exceptions. Long model runs no longer
prevent navigation because polling is isolated to the active fragment.

## Benchmark integrity

The P6 Olist-60 and Spider-200 scores remain valid historical evidence for benchmark revision
`1509faa`, generator v4 and corrector v3. This hardening changes prompt and grounding behavior, so it
does not inherit those accuracy numbers. A new accuracy claim requires a fresh locked-manifest run;
no gold benchmark data is imported by runtime code.
