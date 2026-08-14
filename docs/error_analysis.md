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

The completed laptop-stratified P6 release contains 200 cases across all 20 Spider-dev databases:
100 regression and 100 disjoint holdout. It scored 130/200 (65.00%) with 200/200 typed terminal
states and 199/200 valid candidates. The 70 failures remain in the denominator:

- `EXECUTION_MISMATCH`: 68 cases (97.14% of failures). The SQL executed safely but returned a
  different result, so the main research bottleneck is semantic generation rather than runtime
  reliability.
- `UNKNOWN_RUNTIME_ERROR`: 1 case. The candidate failed during the runtime path and was retained.
- `WRITE_BLOCKED`: 1 case. Layer 4 correctly refused a candidate classified as unsafe; safety was
  not weakened to improve the benchmark score.

Accuracy decreases with structural difficulty: easy 83/107 (77.57%), medium 27/53 (50.94%), hard
16/29 (55.17%), and extra-hard 4/11 (36.36%). The weakest database slices with at least ten cases
are `dog_kennels` and `student_transcripts_tracking` at 40%; the strongest are
`concert_singer`, `flight_2`, and `pets_1` at 90%. Holdout (67/100) is slightly above regression
(63/100), so this run shows no aggregate holdout collapse, but the sample is not an official hidden
Spider leaderboard evaluation.

Olist application fitness is intentionally separate. The same P6 revision scored 57/60 (95.00%):
the three remaining result mismatches are application-level semantic errors, while correction
recovered 6/6 attempted cases without changing the benchmark denominator. The P6 evidence and UI
display these two evaluations separately and never blend their scores.
