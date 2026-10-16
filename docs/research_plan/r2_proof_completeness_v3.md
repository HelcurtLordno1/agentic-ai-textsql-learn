# R2 proof-completeness and benchmark reliability plan

Status: implementation gate, not yet benchmark-verified.

## Objective

Promote a challenger only when the entire executable query meaning is represented by one typed,
catalog-backed contract. The change must be schema-driven and compositional; benchmark IDs, gold
SQL, expected rows, and prompt exceptions are forbidden in runtime code. The guarded R2 workflow
must preserve checkpoints, distinguish expected quality stops from infrastructure failures, retain
both tmux panes after exit, and emit an atomic machine-readable phase status.

## Evidence from `r2-monotonic-v3`

The 45-case shadow phase completed without a resource or timeout incident. Its proof family had 23
paired samples, 16 correct challengers, six improvements, and seven regressions, so certification
correctly refused promotion. The regressions reduce to three systemic causes:

1. **Partial intent called complete.** Entity recognition was treated as proof of the requested
   metric. This confused entity identity with dimensions, dropped comparison/null constraints, and
   let generic payment/order counts stand in for derived populations.
2. **Ambiguous count language.** Bare “bao nhiêu/number of” overrode explicit AVG/MAX semantics,
   while count normalization discarded dimensions such as state or payment type.
3. **Proof mutation after compilation.** A model corrector could replace deterministic compiler SQL,
   and arbitration checked the incumbent against the proof but did not check the final challenger.

## Runtime invariants

- `PROVEN` means one complete output shape, aggregate or frequency ranking, with every detected
  metric, grain, dimension, filter, comparison, null predicate, ordering, and limit represented.
- Explicit AVG/MIN/MAX semantics outrank generic count wording.
- COUNT DISTINCT over a dimension resolves a unique schema column from the entity-owned table; it
  never silently falls back to the entity identity.
- A derived population can compose with a metric only on one physical owner. A derived COUNT rule
  cannot override an explicitly requested AVG/MAX metric.
- Explicit comparison or NULL language that is not represented by a typed predicate makes the
  binding `INCOMPLETE`.
- Deterministic proof SQL is terminal: no model correction may rewrite it. Safety policy, bounded
  read-only execution, and exact SQL-vs-binding validation still apply.
- Arbitration marks a challenger certifiable only when it succeeded, came from the deterministic
  proof compiler, has an accepted typed plan, and its final SQL satisfies the binding.
- Shadow certification counts only certifiable pairs. Rejected challenger artifacts remain visible
  for diagnostics but cannot lower or inflate proof-family statistics.

## Implementation gates

1. Repair count/operator precedence and preserve distinct dimensions in the deterministic
   decomposer.
2. Add schema-derived dimension resolution, metric-plus-derived-predicate composition, and generic
   unresolved-constraint detection to semantic binding.
3. Add a stable delivery-timestamp NULL rule and natural, concept-level aliases for the existing
   late-delivery and multi-payment derived rules.
4. Prevent correction of proof-compiler output and verify the final challenger against its proof.
5. Make evaluator pairing depend on proof acceptance, not merely challenger process completion.
6. Harden tmux logging/retention and write atomic pipeline phase status. Include all operational
   scripts in the source digest.
7. Run focused deterministic tests, offline semantic construction/replay, `uv lock --check`,
   `uv pip check`, `git diff --check`, then mandatory `make check`.
8. Only after all prior evidence passes may a fresh evaluation ID run one guarded pilot and then the
   full shadow/certification/enforce workflow.

## Dependency decision

The current lock resolves cleanly and installed packages are mutually compatible. Available major
updates to SQLGlot, mypy, Plotly, and other transitive UI packages are intentionally excluded from
this gate: they change parser/type/UI behavior, add unrelated variables, and do not address any R2
failure. Future upgrades must be one package at a time with lock diff, full checks, and a separate
source-locked evaluation ID.

## Completion criteria

- All seven observed regression shapes are either compiled to a complete typed meaning or rejected
  as `INCOMPLETE`; none may be admitted through a partial entity proof.
- Every challenger counted for certification has zero SQL-vs-proof contradictions and identifies
  the deterministic compiler as producer.
- Offline proof replay has zero regressions and retains at least five samples over at least three
  proof kinds with at least one improvement.
- `make check` passes. This gate remains `IN_PROGRESS` until a fresh guarded benchmark produces a
  certification and the 60-case enforce report; offline evidence alone cannot mark it `VERIFIED`.
