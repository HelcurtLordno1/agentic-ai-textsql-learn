# R2 semantic construction plan

**Status:** `IN_PROGRESS`

**Scope:** Paper II / DIN-SQL transfer on top of the frozen P6 baseline

**Rule:** Olist-60 and Spider evaluation questions are holdout evidence, not construction inputs.

## 1. Method being developed

The method is **evidence-backed semantic intermediate representation with adaptive DIN-SQL
routing**. It transfers DIN-SQL's decomposition boundary—schema linking, difficulty classification,
query decomposition and correction—but adapts it to a local 14B model and the laptop budget.

```text
question + versioned domain semantics + introspected schema
    -> SemanticBinding(PROVEN | INCOMPLETE | AMBIGUOUS)
    -> compact schema context containing every required owner/column
    -> typed ClausePlan(aggregate, predicates, grain, joins, dependencies)
    -> consistency validation
    -> PROVEN scalar: deterministic SQLGlot compilation
       unsupported EASY: frozen baseline generation
       validated complex: DIN-SQL generation
    -> normal policy, execution and bounded correction
```

This is not a growing list of Python branches for benchmark sentences. Business meaning lives in a
versioned, schema-validated catalog. Runtime code is a generic resolver/compiler over typed rules.
The deterministic path is fail-closed: if the whole scalar meaning is not proven, it emits no SQL.

## 2. Advantage over the frozen baseline

| Concern | Frozen baseline | R2 construction |
|---|---|---|
| Meaning | free-text `LogicalPlan` and prompt interpretation | typed aggregate, predicate, owner and evidence IDs |
| Domain grain | glossary is prompt context | executable semantic metadata validated against the live catalog |
| Easy queries | model call can vary or select the wrong owner | zero-generation-call compilation only for complete proof |
| Unknown/ambiguous wording | model may guess | `INCOMPLETE`/`AMBIGUOUS` and baseline hand-off |
| Complex queries | same broad generation path | `NON_NESTED`/`NESTED` clause and dependency plans |
| Integrity | human-readable clauses can drift | binding, clause fields, evidence and schema must agree |
| Evaluation | final execution result | final result plus clause/owner/join/plan agreement |

The expected gain is lower variance and fewer wrong-grain/owner/value errors in the covered semantic
families, while retaining baseline behavior outside that coverage. No gain is claimed before the
paired benchmark gate.

## 3. Construction invariants

1. A `PROVEN` binding has exactly one explicit aggregate and all required identifiers.
2. Every semantic catalog identifier must exist in the introspected database at runtime startup.
3. Canonical enum values and derived grains live in YAML, never in question-specific Python code.
4. The scalar compiler reads typed fields only; display strings cannot alter generated SQL.
5. Binding and clause aggregate/predicates must be structurally equal.
6. Required columns must be present in the bounded `SchemaContext`.
7. Multi-table, grouped, ranked, temporal, set and unresolved-qualified questions never enter the
   deterministic scalar compiler.
8. Lack of a semantic catalog does not damage cross-domain execution: EASY falls back to baseline;
   validated complex plans may still use the DIN path.
9. Runtime remains gold-blind and imports neither `agentic_text2sql_eval` nor benchmark answers.
10. No research module becomes `VERIFIED` without reproducible `make check` and paired benchmark
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
| C3 distribution tests | positive, metamorphic and fail-closed matrix | passed 20-case matrix |
| C4 repository gate | full `make check`; no Ollama/GPU run | passed: 219 tests |
| C5 frozen benchmark | guarded Olist first, then Spider only if Olist threshold holds | pending |

For C5, use only the approved guarded wrapper, batch size one, continuous resource monitoring,
checkpointing, unload/cooldown and the thresholds in `AGENTS.md`. Stop Olist immediately if its final
upper bound falls below 57/60; record the negative result instead of adding case-specific fixes.
Only one architecture-level revision may follow a failed benchmark, justified by a failure-family
analysis on the development split. Otherwise reject R2 promotion and keep the frozen baseline.

Promotion remains: medium+hard Spider +5 percentage points, overall +2 points, easy loses at most one
case, Olist does not regress below 57/60, and end-to-end p95 rises no more than 20%. Until then R2 is
an experiment, not the project champion.
