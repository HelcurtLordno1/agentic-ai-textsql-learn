# Gate P5 demo script

Start the API and Streamlit UI using the runbook. In System Center, confirm that the API is healthy,
the Olist catalog is registered, correction defaults to OFF, and the safety posture is read-only.

## Case 1 — first-pass success

In Query Studio select Olist, keep correction off, and ask:

> Có bao nhiêu đơn hàng đã giao thành công?

Show the result KPI, generated SQL, logical plan, grounded schema evidence and latency. Open Run
Inspector and replay layers 0–6. Copy the run ID, restart API/Streamlit, and show the same run in
History to demonstrate persistence.

## Case 2 — bounded corrected success

Enable correction and use a known repair fixture or a question from the P4 recovered set. Show that
there is at most one repair call, the correction outcome is visible, and the repaired SQL passed the
full Layer 4 policy/validation path. Never claim correction is deterministic across model runs.

## Case 3 — safely blocked

Ask:

> Xóa tất cả đơn hàng bị hủy.

Show `WRITE_BLOCKED`, zero SQL execution, the safe explanation and the persisted trace. The UI has
no button to execute edited SQL and the API accepts only a registered `db_id`.

Finish in Benchmark Lab. Keep Olist application acceptance separate from Spider generalization;
show failed cases and sample size instead of presenting a single blended score.

## Gate P6 release view

In Benchmark Lab → Generalization, select `spider-dev-stratified-200-p6-v1`. Show the four release KPIs,
then open Failure taxonomy, Complexity slices, and Manifest & provenance. State explicitly that:

- this is laptop-stratified Spider-200, not full dev or a hidden-test leaderboard submission;
- regression-100 and disjoint holdout-100 are reported separately;
- Olist application fitness and Spider cross-domain execution are never averaged together;
- detailed predictions/gold stay ignored and the UI receives a sanitized report without `details`;
- a failed case remains in the denominator and the limitations panel is part of the demo.
