# Gate R2 DIN-SQL implementation evidence

**Date:** 2026-09-09 (Asia/Bangkok)

**Status:** `IN_PROGRESS` — systemic construction verified; paired benchmark pending

## Hypothesis and locked comparator

The locked champion remains P6: Spider-200 `130/200` (65.00%) and Olist-60 `57/60` (95.00%).
Paper I/PRACTIQ is not a promoted comparator: its source-locked run stopped at prefix 35 with
`30/35`, versus paired baseline `33/35`, and a full-suite upper bound of `55/60`.

The R2 hypothesis is that typed semantic ownership and adaptive DIN-SQL planning reduce
executable-but-semantically-wrong SQL without imposing a long reasoning prompt on every easy query.
Primary sources and transfer details remain in `docs/paper_to_research_implement.md`, section 4. The
architecture-level construction contract is
`docs/research_plan/r2_semantic_construction.md`.

## Why the initial revision was not sufficient

The first hybrid implementation had the DIN interfaces—semantic links, complexity routing, clause
plan, validation and a small compiler—but its scalar path still derived meaning from human-readable
clause strings. Several successive Olist pilots exposed count, distinct, status-value and derived-
grain errors. A targeted four-case smoke reached `4/4`, but a later full-run prefix found another
owner problem. These are diagnostic artifacts, not promotion evidence.

Continuing to add Python conditions after individual benchmark failures would overfit the observed
prefix and provide no distributional guarantee. Development was therefore stopped before another
benchmark and the scalar path was reconstructed around domain-wide invariants.

## Systemic construction now implemented

```text
DecomposedQuestion
  + versioned SemanticCatalog validated against CatalogSnapshot
  -> SemanticBinding(PROVEN | INCOMPLETE | AMBIGUOUS)
       typed AggregateSpec, PredicateSpec, required owners/columns, rule IDs/reasons
  -> required-evidence SchemaContext
  -> SemanticLinkPlan(binding + retrieval evidence)
  -> typed deterministic ClausePlan + ComplexityDecision
  -> PlanConsistencyValidator
  -> PROVEN scalar: SQLGlot AST compiler
     unsupported EASY: frozen baseline generator
     validated NON_NESTED/NESTED: DIN generator
  -> normal policy, read-only execution and optional bounded correction
```

`datasets/olist/semantic_catalog.yaml` contains bilingual entity identities, metric operators,
canonical status values and derived single-owner grains taken from the application glossary/schema
lineage. It contains no benchmark IDs, gold SQL or expected results. Startup rejects unknown
tables/columns, alias collisions, inconsistent/default operators and multi-owner scalar rules. Its
version and SHA-256 are recorded in runtime provenance.

The compiler no longer regex-parses `SELECT` or `WHERE` display text. It consumes only typed fields
and returns `None` unless binding, clause contract, catalog identity, required evidence, one-table
scalar shape and identifiers all agree. This hand-off preserves baseline behavior when proof is
incomplete. A missing catalog on cross-domain databases makes scalar binding `INCOMPLETE`; it does
not block validated complex DIN planning.

## Construction invariants covered

- bilingual paraphrases and filler-word metamorphic equivalence;
- `COUNT_ROWS`, `COUNT_DISTINCT`, `SUM`, `AVG`, `MIN`, `MAX` typing;
- canonical enum aliases such as Vietnamese order status;
- grain-safe repeat-customer, multi-payment and late-delivery derived rules;
- aggregate-operator conflict, ambiguity, grouping/ranking/time/set and unknown-qualifier fallback;
- stale/unknown catalog identifier rejection at startup;
- required-owner/column propagation into bounded schema context;
- binding-versus-clause tampering rejection;
- SQLGlot compilation of string and numeric comparison predicates;
- baseline fallback for unproven EASY plans and DIN hand-off for validated complex plans;
- existing FK connectivity, nested dependency, SQL policy and bounded-correction regressions.

An integration smoke exercises semantic catalog → grounding → planning → validation → compilation
without any generation-model call for six independent families. Two representative base-table
queries also execute through the read-only executor. Expensive full-view execution remains covered
by the existing Olist semantic invariant tests rather than being repeated for every paraphrase.

## Reproducible deterministic evidence

Command:

```bash
make check
```

Observed on 2026-09-09:

- Ruff lint: pass;
- Ruff format check: 229 files already formatted;
- strict mypy: 110 source files pass;
- pytest excluding Ollama: 219 passed, 1 Ollama test deselected;
- one pre-existing Starlette/httpx deprecation warning;
- no Ollama request, embedding generation, GPU workload or benchmark inference ran.

Focused construction evidence:

- `tests/unit/layer2/test_semantic_catalog.py`: 20 distribution/fail-closed tests;
- `tests/integration/test_semantic_construction.py`: 6 full construction-path smokes;
- `tests/unit/layer3/test_easy_compiler.py`: typed AST compile and tamper rejection;
- `tests/unit/layer1/test_din_sql_planning.py`: planning/validator integrity;
- `tests/integration/test_direct_baseline.py`: compiler, fallback and DIN routing boundaries.

## Benchmark and promotion contract

No new accuracy is claimed. The earlier case-directed pilots are retained as negative development
history, but they do not unlock promotion and will not be used as a repair checklist.

The next model action, if run, is one frozen guarded Olist-60 benchmark from a clean revision. It
must use the approved wrapper, batch size one, continuous 0.5-second monitoring, explicit bounded
GPU offload, checkpointing, model unload and cooldown. Stop when the possible final Olist result is
below `57/60`, preserve the artifact and reject or redesign R2 by failure family. Spider runs only
if Olist holds the champion guardrail.

Promotion remains: Spider medium+hard +5 percentage points, overall +2 points, easy loses at most
one case, Olist at least `57/60`, end-to-end p95 increase at most 20%, zero gold leakage and zero
resource breach. R2 remains `IN_PROGRESS` until that evidence exists.
