# R2 semantic construction plan

**Status:** `IN_PROGRESS`

**Scope:** Paper II / DIN-SQL transfer on top of the frozen P6 baseline

**Rule:** Olist-60 and Spider evaluation questions are holdout evidence, not construction inputs.

## 1. Method being developed

The method is **evidence-backed semantic intermediate representation with adaptive DIN-SQL
routing**. It transfers DIN-SQL's decomposition boundary—schema linking, difficulty classification,
query decomposition and correction—but adapts it to a local 14B model and the laptop budget.

```text
question
    -> frozen P6 planner
    -> AdaptiveRouteDecision
       BASELINE_PRESERVE (default)
         -> unchanged P6 grounding -> generator -> correction
       DIN_SQL_ENHANCE (explicit complex dependency only)
         -> semantic links + bounded schema context
         -> schema-bounded DIN decomposition model
         -> typed ClausePlan(grain, joins, predicates, dependencies)
         -> consistency validation -> DIN generator/correction
```

This is not a growing list of Python branches for benchmark sentences. Business meaning lives in a
versioned, schema-validated catalog. Runtime code is a generic resolver/compiler over typed rules.
The earlier deterministic scalar compiler remains independently tested research code, but no longer
replaces the P6 EASY path. Catalog coverage is not a sufficient activation condition: a compiler can
be internally consistent while changing population grain or colliding with mature validation. The
adaptive policy defaults to baseline preservation and never routes from benchmark identity.

## 2. Advantage over the frozen baseline

| Concern | Frozen baseline | R2 construction |
|---|---|---|
| Meaning | free-text `LogicalPlan` and prompt interpretation | typed aggregate, predicate, owner and evidence IDs |
| Domain grain | glossary is prompt context | executable semantic metadata validated against the live catalog |
| Easy queries | mature P6 behavior at 57/60 | preserved planner, grounding, generator and corrector |
| Unknown/ambiguous wording | model may guess | `INCOMPLETE`/`AMBIGUOUS` and baseline hand-off |
| Complex queries | same broad generation path | schema-bounded `NON_NESTED`/`NESTED` decomposition only when explicitly activated |
| Integrity | human-readable clauses can drift | binding, clause fields, evidence and schema must agree |
| Evaluation | final execution result | final result plus clause/owner/join/plan agreement |

The expected gain is lower variance and fewer wrong-grain/owner/value errors in the covered semantic
families, while retaining baseline behavior outside that coverage. No gain is claimed before the
paired benchmark gate.

## 3. Construction invariants

1. `BASELINE_PRESERVE` is the default; catalog coverage cannot activate DIN or compilation.
2. A `PROVEN` binding has exactly one explicit aggregate and all required identifiers.
3. Every entity/metric rule declares source grain; weighted averages declare their weight column
   and requested rounding is carried as typed data.
4. Every semantic catalog identifier must exist in the introspected database at runtime startup.
5. Canonical enum values and derived grains live in YAML, never in question-specific Python code.
6. The scalar compiler reads typed fields only; display strings cannot alter generated SQL.
7. Binding and clause aggregate/predicates must be structurally equal.
8. Required columns, including weight columns, must be present in the bounded `SchemaContext`.
9. Multi-table, grouped, ranked, temporal, set and unresolved-qualified questions never enter the
   deterministic scalar compiler.
10. Lack of a semantic catalog does not damage cross-domain execution: EASY stays on baseline;
   validated complex plans may still use the DIN path.
11. Semantic validation consumes proven typed lineage before lexical compatibility guards.
12. Runtime remains gold-blind and imports neither `agentic_text2sql_eval` nor benchmark answers.
13. No research module becomes `VERIFIED` without reproducible `make check` and paired benchmark
    evidence.

## 4. Domain ontology construction

The Olist catalog is derived from stable application semantics already documented in
`business_glossary.yaml`, `metric_definitions.md`, raw schema and derived view lineage. It covers
entity identities, monetary/review/delivery metrics, order-status enum values and derived grains
such as repeat customers, multi-payment orders and late deliveries. Aliases are bilingual semantic
families; they contain no benchmark IDs, gold SQL or expected results.

An operator is part of the typed intent, not inferred from a retrieved numeric column. Explicit
`SUM`/`AVG`/`MIN`/`MAX` wording is accepted only when the metric rule allows it. Count-versus-metric
conflicts, unknown qualifiers, multiple owners and multiple rule matches fail closed.

## 5. Test construction matrix

The pre-benchmark suite is distribution-oriented:

- paraphrases across English and Vietnamese for every rule family;
- filler-word metamorphic equivalence;
- aggregate-operator variations over the same metric;
- canonical enum alias equivalence;
- derived-view predicate and grain checks;
- ambiguity, unknown qualifier, grouped/ranked/time/set negative cases;
- stale/unknown table and column startup rejection;
- typed-contract tampering rejection;
- deterministic compiled SQL and execution on the local Olist database;
- hybrid fallback tests proving unsupported semantics still use the baseline path;
- existing DIN join, nested dependency, policy and correction regressions.

Tests may use newly authored paraphrases and schema fixtures. They must not enumerate Olist-60 or
Spider holdout questions as implementation targets.

## 6. Gates and benchmark decision

| Gate | Required evidence | Current state |
|---|---|---|
| C1 contracts/catalog | strict Pydantic contracts; schema validation | passed deterministic tests |
| C2 runtime integration | startup → grounding → planner → validator → compiler/fallback | passed 6-path smoke |
| C3 distribution tests | positive, metamorphic and fail-closed matrix | passed route/semantic matrix |
| C4 repository gate | full `make check`; no Ollama/GPU run | passed: 235 tests |
| C5a initial frozen benchmark | revision `f70d191`, guarded Olist | rejected at 8/12; upper bound 56/60 |
| C5b adaptive redesign | baseline-preserve + complex-only DIN | construction tests pass; benchmark pending |

For C5, use only the approved guarded wrapper, batch size one, continuous resource monitoring,
checkpointing, unload/cooldown and the thresholds in `AGENTS.md`. Stop Olist immediately if its final
upper bound falls below 57/60; record the negative result instead of adding case-specific fixes.
This adaptive redesign is the one permitted architecture-level revision after the failed benchmark.
It is constructed from failure families—activation boundary, grain/lineage and stage ownership—not
from benchmark IDs. Once frozen, its benchmark is recorded without case-directed repair. If Olist
again falls below 57/60, reject R2 and keep the frozen baseline.

Promotion remains: medium+hard Spider +5 percentage points, overall +2 points, easy loses at most one
case, Olist does not regress below 57/60, and end-to-end p95 rises no more than 20%. Until then R2 is
an experiment, not the project champion.
