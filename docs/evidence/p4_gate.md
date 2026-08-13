# Gate P4 evidence — 2026-08-13

## Scope and decision

Gate P4 implements the missing Layer 4 validation dependency and Layer 5 guided correction. The
gate is `VERIFIED` for a bounded, gold-blind, feature-flagged correction path. It is not a claim
that every stochastic model run repairs every eligible failure.

## Validation foundation

- `ValidationReport` now distinguishes `VALID`, `SUSPICIOUS`, and `FAILED`, carries stable signals,
  and explicitly marks repair eligibility.
- Execution-result validation checks scalar aggregate row/column shape without gold data.
- Conservative semantic rules cover top-k shape, aggregate intent, returning-customer identity,
  late-delivery population, and declared join-grain risk.
- Empty results remain warnings rather than automatic failures.
- Runtime source does not import `agentic_text2sql_eval`; gold rows and gold SQL stay in the offline
  evaluator.

## Bounded correction

- Rule-first classifier and typed immutable `CorrectionPlan` precede the local Corrector Agent.
- The corrector returns a complete `SqlCandidate`; every repaired candidate re-enters SQL parsing,
  AST policy, read-only execution, result validation, and semantic validation.
- Default live configuration is one repair and one correction LLM call. The hard supported maximum
  remains two repairs.
- The controller stops on repair/call budget, shared deadline, repeated SQL, repeated error,
  non-eligible class, or model-contract failure. Policy violations and timeouts are not repaired.
- Correction is opt-in through `scripts/run_smoke.py --correction on`; correction-off preserves the
  P3.1 baseline path.

## Deterministic verification

Focused tests exercise result shape, semantic signals, successful repair, full revalidation,
valid-candidate no-op, policy no-repair, repeated-SQL stop, deadline stop, one-call budget, database
immutability, and prompt gold separation. Existing safety/property tests continue to cover parser,
authorizer, timeout, result caps, and database checksum.

Final `make check` passes Ruff lint, Ruff format, strict mypy over 96 source files, and pytest with
the explicit live-model marker excluded. The focused P4 suite reports 10 passing tests.

## Frozen Olist correction off/on ablation

Both sides use the same 20-case Olist smoke set, semantic grounded catalog, Qwen3
`qwen3:14b-q4_K_M`, generator prompt v2, and no gold feedback during inference.

| Metric | Correction off (P3.1) | Correction on (P4 live run) |
|---|---:|---:|
| Result accuracy | 14/18 (77.78%) | 17/18 (94.44%) |
| Typed terminal | 20/20 | 20/20 |
| Expected status | 19/20 | 19/20 |
| P50 total latency | 34.68 s | 10.40 s |
| P95 total latency | 46.40 s | 23.07 s |
| Correction attempts | 0 | 4 |
| Recovered | 0 | 3 |
| Correct-to-wrong regressions | 0 | 0 |

The P4 run recovered:

- `olist_vi_007`: removed the extra aggregate output column and returned `[[2997]]`;
- `olist_vi_009`: removed the incorrect delivered-status population restriction and returned
  `[[7827]]`;
- `olist_vi_013`: repaired the customer alias/join and returned `[['SP', 41746]]`.

`olist_en_010` remained incorrect. Validation caught the non-scalar average result, the corrector
repeated the same SQL, and the controller stopped with `REPEATED_SQL` after exactly one call. The
run therefore reports 3/4 recovery (75%): two `SEMANTIC_MISMATCH` attempts recovered, the one
`UNKNOWN_COLUMN` attempt recovered, and the one `RESULT_SHAPE_MISMATCH` attempt did not.

The lower latency in this run is reported, not attributed to correction: model warm state and local
runtime conditions differ from the historical P3.1 run. It is evidence that the 60 s deadline was
not exceeded, not evidence that correction inherently accelerates inference.

## Repeatability limitation

A separate diagnostic rerun limited to the four historical failure questions regenerated planner
and generator outputs and recovered only 1/3 triggered repairs; another case ended in a repeated
error. This run is intentionally not used as the frozen off/on score, but it demonstrates model
variance. Consequently correction remains opt-in after P4. Multi-run/seed stability and the
roadmap's reviewed Olist-60 holdout remain required before portfolio-complete or default-on status.

## Gate result

- No repair/call budget overflow: pass.
- Policy no-repair and read-only checksum: pass.
- Gold leakage/dependency boundary: pass.
- Recovery report by trigger category and stop reason: pass.
- Correction-on accuracy regression: none; net gain 3/18 on the frozen run.
- End-to-end P95 within 60 s: pass.

Gate status: `GATE_P4_VERIFIED_FEATURE_FLAGGED`.
