# R2 monotonic champion--challenger architecture

**Status:** `IN_PROGRESS`; H3.1--H6 construction gates passed, H7 benchmark not run

**Promotion target:** at least 58/60 on the source-locked Olist suite. A score of 57/60 only ties
the frozen P6 champion and is non-regression evidence, not an improvement.

## 1. Causal diagnosis

Revision E did not miss the target because it lacked enough aliases or retries. It violated a
stronger systems invariant: routing to a specialist preserved the P6 logical plan, but discarded
the P6 SQL candidate before the specialist had demonstrated a better candidate. Consequently a
correct baseline answer could become a terminal grounding, planning, generation, or validation
failure. Planner-only fallback cannot make accuracy monotonic.

The observed 28/31 prefix supports five narrower findings:

1. Typed proof can repair real population and output-shape errors, but proof coverage is not proof
   precision. An alias match does not establish population owner, row grain, aggregation order,
   filters, or result shape.
2. Semantic evidence is duplicated across catalog text, clause plans, SQL checks, and question
   regexes. These copies can disagree; case 31 was generated from valid lineage and rejected by an
   independent lexical approximation.
3. Specialist work consumes the same deadline as recovery. A late fallback can be logically sound
   and still unusable because no generation/correction budget remains.
4. Result-correctness cannot generally be inferred from executability or SQL confidence. The
   runtime therefore needs a conservative commit rule, not a confidence-based best-of-N selector.
5. Olist business views can improve Olist but do not transfer by themselves. Spider transfer must
   come from database-independent operator contracts and schema-derived evidence, with optional
   domain catalogs treated as bounded facts rather than a complete ontology.

The 28/31 stopped prefix is not evidence that 57/60 is likely. It only identifies a regression
mechanism and three observed failures. Accuracy remains an experimental outcome.

## 2. Target control flow

```text
question
  -> frozen P6 plan, grounding, candidate and validation = incumbent
  -> specialist proof/plan/candidate in shadow = challenger
  -> typed arbitration
       KEEP_INCUMBENT
       PROMOTE_CHALLENGER
       ABSTAIN_OR_TYPED_FAILURE
  -> one selected candidate enters the bounded correction loop
```

This is not unconstrained candidate sampling. There is one frozen incumbent and at most one
structurally different challenger. The challenger may replace an accepted incumbent only after a
pre-registered route class has passed shadow precision gates and the runtime can name the incumbent
obligation that the challenger repairs. Execution success alone is never sufficient.

Required cross-layer evidence is a single immutable chain:

```text
question span -> semantic role -> schema owner -> source grain -> operator/clause
              -> SQL AST lineage -> result grain
```

Validators consume that chain. They must not reconstruct the same claim from lexical occurrence.

## 3. Roadmap gates

### H3.1 -- fail-closed specialist control plane

- Preserve the baseline plan before specialist work.
- On specialist grounding failure, DIN planning failure, or rejected DIN plan, discard specialist
  state and resume frozen baseline grounding/generation exactly once.
- Record a stage-specific route signal; never retry the failed specialist stage.
- Construction gate: deterministic integration tests plus `make check`.

This gate improves availability, not measured accuracy. Generation- and candidate-validation
fallback remain outside H3.1 and must not be claimed as complete.

Construction evidence (2026-09-14): integration tests reproduce specialist grounding failure and
plan-consistency rejection, then assert one baseline grounding/generation path and an auditable
stage signal. `make check` passed Ruff, format, strict mypy on 111 source files, and 266 non-Ollama
tests (one Ollama test deselected). No local model or acceptance suite was run.

### H4 -- shadow candidate ledger

- Produce the incumbent normally and return it unchanged.
- Build a challenger only when resource admission leaves an explicit reserve for selection and
  correction. Never run generation and embedding models concurrently.
- Persist both candidate fingerprints, route, proof obligations, validation signals, latency, and
  resource telemetry without gold data.
- Add an offline replay evaluator that opens expected results only after both predictions are
  durable.
- Gate: 100% incumbent output equivalence with frozen P6 on deterministic fixtures; no user-visible
  specialist selection.

**Construction status:** implemented. Shadow mode persists both bounded candidates/results and
always selects the incumbent. Offline evaluation reports paired transitions and proof-kind slices.

### H5 -- conservative typed arbitration

- Define `CandidateDecision` and exhaustive reason codes.
- Promote only a fully validated challenger from a shadow-certified proof class when it repairs a
  named incumbent contradiction and introduces no unproven obligation.
- Keep the incumbent on disagreement that cannot be decided structurally. Do not use model-stated
  confidence as a promotion signal.
- Gate each proof class independently with paraphrase, adversarial negative, schema-tamper, and
  cross-domain structural variants. Optimize promotion precision before route recall.

**Construction status:** implemented for aggregate and frequency-ranking proof kinds. Certification
uses only dev/regression, requires support >=5, challenger accuracy 100%, at least one improvement
and zero regressions. Runtime accepts only a closed operator vocabulary, never case IDs.

### H6 -- deadline and resource partition

- Reserve time before specialist admission for incumbent generation, validation, and at most one
  correction.
- Refuse specialist admission when the reserve cannot be honored.
- Keep explicit local-model GPU offload and the existing guarded runner requirements. No acceptance
  or local-LLM suite runs outside the approved wrapper.

**Construction status:** implemented with sequential model use, a 300-second admission budget,
45-second challenger reserve, external 360-second batch stop, one-case checkpointing and the
`olist-paper1-ultrasafe` profile.

### H7 -- locked evaluation

1. Run `make check` and offline shadow replay.
2. Run a guarded one-case pilot from safe idle state.
3. Run source-locked development/regression with a new evaluation identity and predeclared kill
   criterion.
4. Open the full Olist suite only while 58/60 remains reachable. Do not tune from holdout.
5. Promote only at >=58/60 with no systematic paired P6 regression and complete resource evidence.
6. Then run the locked Spider slice to measure transfer; do not use Spider aggregate accuracy to
   excuse an Olist grain failure.

**Construction status:** one-command runner implemented with source digest lock, dev/regression
shadow certification, separate enforce artifacts and the 58/60 kill criterion. It has not been run;
there is no new score or promotion claim.

## 4. Spider transfer contract

Portable components are operator shapes (`COUNT_ROWS`, `COUNT_DISTINCT`, aggregate, frequency
ranking, grouped scalar, anti-join), catalog identity, PK/FK topology, nullability, uniqueness, AST
scope, and lineage. Olist aliases and named semantic views are domain adapters and must be absent or
optional on Spider.

Every promoted abstraction needs a synthetic schema transformation test: rename tables/columns,
split or merge a relation while preserving meaning, and tamper with the claimed identity/grain.
The proof must either rebind from valid metadata or become `INCOMPLETE`; silently retaining the old
owner is a transfer failure.

## 5. Claim boundary

- Revision H diagnostics on known cases are diagnostic evidence only.
- H3.1 construction cannot establish 57/60, 58/60, or Spider gain.
- No architecture can guarantee a benchmark result before the locked run.
- The falsifiable goal is monotonic integration: specialist failures must no longer erase an
  available incumbent, and specialist promotion must earn its regression budget by measured
  high-precision shadow evidence.

Full construction evidence (2026-09-15): `make check` passed Ruff, format, strict mypy on 114 source
files, and 281 non-Ollama tests (one Ollama test deselected). The deep research report and source
mapping are in `docs/research_plan/r2_architecture_deep_research.md`.
