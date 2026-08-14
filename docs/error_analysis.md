# Error analysis

## Phase 2 direct full-schema baseline

The first verified live baseline scored 14/18 exact-result query cases (77.78%). All 20 cases ended
with typed terminal states. Remaining failures are retained rather than corrected inside this
baseline:

- `olist_vi_007` customer identity: semantically correct count but emitted an extra duplicate count
  column, so strict result shape failed.
- `olist_vi_009` delivery population: generated SQL restricted `order_status='delivered'` and
  returned 7,826 instead of the canonical non-null delivered-timestamp population's 7,827.
- `olist_en_010` review grain/schema: referenced `review_score` on `order_review_summary`; policy
  blocked the unknown column before execution.
- `olist_vi_013` state join: omitted the customer join and referenced `customer_state` on orders;
  policy blocked it before execution.

These cases become inputs for retrieval and correction analysis in later gates. Gold results were
not used to trigger retries.

## Gate P6 release taxonomy

The Spider release evaluator assigns every incorrect case to one auditable final category. Typed
workflow failures retain their normalized error class (`UNKNOWN_COLUMN`, `JOIN_ERROR`, timeout,
policy stop, and so on). A successfully executed candidate with different rows is
`EXECUTION_MISMATCH`; an evaluator-side SQLite failure is `EVALUATOR_EXECUTION_ERROR`. No case is
removed from the denominator.

The final P6 evidence records the top categories and complexity/database slices from the complete
1,034-case report. Until that guarded report exists, this section intentionally contains no claimed
Spider accuracy or category counts.
