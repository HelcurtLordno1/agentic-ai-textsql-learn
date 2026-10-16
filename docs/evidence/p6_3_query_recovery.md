# Post-P6 free-form query recovery — 2026-08-17

## Incident

Run `e4e905f4-3a07-452e-9962-e676ec5b93d3` asked:
`Có bao nhiêu khách hàng quay lại theo customer_unique_id? cho tôi biết đủ`.
The generator referenced `customer_unique_id` inside an `olist_orders_dataset` subquery even though
that owner exists only in the customer table. Execution ended `UNKNOWN_COLUMN` after 71.92 seconds,
and Layer 5 was skipped because interactive correction defaulted off.

A controlled correction-on reproduction exposed a second failure: the corrector repaired ownership
but returned one `COUNT=1` row per qualifying customer. The result validator correctly raised
`SCALAR_AGGREGATE_ROW_COUNT`. A subsequent generator produced the canonical semantic-view SQL, but
the old semantic validator incorrectly required the identity column text to appear in SQL even
though `customer_order_facts` is already grouped by that identity. This was a validator false
positive, not a database error.

## Architecture changes

- Schema linking evaluates singleton and connected components. Its deterministic score prioritizes
  requested dimensions, then metrics, intent coverage, evidence quality and minimal complexity.
  Plan-matching catalog columns are added within the token budget even if dense top-k omitted one.
- The repeat-customer glossary now declares `customer_order_facts`, `order_count > 1`, and scalar
  `COUNT(*)` as its runtime semantic contract. This is domain metadata, not benchmark gold.
- Generator v6 and corrector v5 require local SELECT/subquery ownership and exactly one output row
  for scalar aggregation. GROUP BY/HAVING groups must be wrapped before counting.
- Layer 4 rejects ambiguous implicit outer-scope columns while retaining explicitly qualified
  correlation. Its returning-customer check accepts the declared semantic view only when the repeat
  filter is present.
- Interactive API/UI correction defaults on with the existing hard cap of one repair. Controlled
  benchmark and ablation callers can still set it explicitly.
- Failed UI runs show attempted SQL, schema context, typed validation error and repair outcome.
  Model confidence is shown as self-reported confidence, explicitly not per-query accuracy.

## Live evidence

Final run `170c567e-4362-4831-97c8-b6e932382ca0` used the exact incident question with the request's
default correction setting. It completed `SUCCEEDED` on the first candidate:

```sql
SELECT COUNT(*) FROM customer_order_facts WHERE order_count > 1
```

The result was one row, one column: `2997`. Grounding contained only
`customer_order_facts(customer_unique_id, order_count)`. Prompt versions were
`generator_v6_scalar_semantic` and `corrector_v5_scalar_semantic`; correction was available but not
needed. End-to-end latency was 71.08 seconds and model confidence was 95%.

The opposite regression case was also rerun end to end as
`dc1c66e3-d579-4a10-8d77-d2ff606fd9e1`: category ranking with separate revenue/freight completed
`SUCCEEDED` first-pass with five rows. It grounded to `olist_order_items_dataset` plus
`olist_products_dataset` with their declared `product_id` FK, not to a dimension-only translation
table or disconnected aggregate view. End-to-end latency was 95.79 seconds and SQLite validation/
execution was 0.362 seconds.

## Accuracy semantics

The 95% value above is model self-confidence, not measured accuracy. This run is deterministically
validated and its value matches the domain's canonical invariant, but general free-form per-query
accuracy is undefined without an independent reference result. P6 Olist/Spider scores remain tied
to their historical benchmark revision; generator v6/corrector v5 require a new locked-manifest run
before any aggregate accuracy claim.

## Verification

The focused schema/prompt/policy/semantic/API/UI suites passed before the final repository gate.
`make check` then completed with Ruff lint and format clean, mypy clean across 105 source files, and
175 tests passed with one explicit Ollama test deselected. Streamlit AppTest rendered Query Studio
and Run Inspector with zero exceptions and confirmed the accuracy disclaimer is visible.
