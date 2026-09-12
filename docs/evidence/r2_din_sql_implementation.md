# Gate R2 DIN-SQL implementation evidence

**Date:** 2026-09-12 (Asia/Bangkok)

**Status:** `IN_PROGRESS` — systemic construction verified; revision `f70d191` rejected by the
paired Olist accuracy gate; adaptive revision `e8fab80` is benchmark-inconclusive because its
guarded pilot timed out before routing or SQL generation

## Hypothesis and locked comparator

The locked champion remains P6: Spider-200 `130/200` (65.00%) and Olist-60 `57/60` (95.00%).
Paper I/PRACTIQ is not a promoted comparator: its source-locked run stopped at prefix 35 with
`30/35`, versus paired baseline `33/35`, and a full-suite upper bound of `55/60`.

The R2 hypothesis is that typed semantic ownership and adaptive DIN-SQL planning reduce
executable-but-semantically-wrong SQL without imposing a long reasoning prompt on every easy query.
Primary sources and transfer details remain in
`docs/research_plan/paper_to_research_implement.md`, section 6. The architecture-level construction
contract is `docs/research_plan/r2_semantic_construction.md`.

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

Observed again after the benchmark report update on 2026-09-11:

- Ruff lint: pass;
- Ruff format check: 230 files already formatted;
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

## Frozen Olist benchmark result

The clean source revision `f70d1912220902326d821557ab3ab5d6a616f39b` was evaluated under the
approved `olist-paper1-ultrasafe` wrapper on 2026-09-11. A one-case pilot passed, then the exact same
checkpoint continued with batch size one, model unload, 60-second cooldown and 0.5-second resource
sampling. The run stopped automatically at case 12:

- Paper II prefix: `8/12` (66.67%);
- paired P6 baseline prefix: `12/12` (100%);
- full-suite upper bound: `8 + 48 = 56/60`, below the `57/60` champion;
- corrections attempted/recovered: `2/0`;
- clause exact and macro clause F1: `12/12` and `1.0`, despite result accuracy `0.6667`;
- macro table/column recall: `0.6667/0.5556`;
- failed cases: `olist_acc_005`, `010`, `011`, `012`.

The failures span fallback timeout, wrong aggregate grain, lineage-blind validator rejection and
incomplete late-delivery predicate binding. They are recorded as failure families, not as a list of
benchmark-ID repairs. The source-locked report is `comparison_new2_to_baseline_vn.md`; local raw
predictions and evaluator reports remain uncommitted by repository policy.

The run used one Qwen3-14B GPU layer and an Administrator hard graphics-clock lock of 300–600 MHz.
Observed peaks were 2.277 GiB system RAM used, zero swap, 1,557 MiB VRAM, 56 C, 45.01 W and 600 MHz.
There was no resource breach, OOM or shutdown. Ollama was unloaded and the hard clock was reset only
after all model work stopped.

Revision `f70d191` is rejected for promotion. Spider was not run because Olist failed its mandatory
non-regression gate. R2 remains `IN_PROGRESS`, not `VERIFIED`; any continuation requires systemic
grain/lineage/predicate invariants or a narrower complex-query-only activation, followed by a fresh
revision and evaluation ID. The stopped checkpoint must not be resumed or blended with a later run.

## One permitted architecture-level redesign

The post-failure redesign does not repair benchmark IDs. It changes the global intervention
boundary: hybrid mode first obtains the frozen P6 logical plan, then a typed gold-blind policy keeps
the default `BASELINE_PRESERVE` route or selects `DIN_SQL_ENHANCE` only for explicit set/nested,
aggregate-dependency, or multi-role grouped structure. Baseline-preserved requests use the original
P6 planner, grounding, generator and corrector; the deterministic semantic compiler cannot replace
them. Complex requests alone add schema links, the previously unused schema-bounded DIN planner
prompt, typed plan validation, and DIN generation/correction.

Semantic aggregate contracts now carry source grain, optional weight columns and requested rounding.
Catalog validation checks those identifiers, the compiler supports weighted averages, and plan
validation requires weight-column evidence. Semantic validation consumes proven derived lineage
before applying legacy lexical guards. Distribution tests cover route invariance, baseline call/path
preservation, complex three-stage hand-off, weighted-grain algebra and lineage compatibility.

This redesign was frozen before evaluation as
`e8fab80582113263fa75e1f625fc7b9729fbe65f`. Its Olist artifact uses a fresh evaluation ID and is
not resumed from `olist-paper2-semantic-f70d191-v1`. Its result must be accepted or rejected as
measured; no failure-directed code change is permitted during a run.

## Adaptive revision guarded-pilot evidence

The fresh evaluation ID was `olist-paper2-adaptive-e8fab80-v1`. The run used the only approved
Qwen3-14B Olist profile: one GPU layer, batch size one, 0.5-second monitoring, per-case unload and
60-second cooldown, with an Administrator graphics-clock lock verified at 300–600 MHz.

`olist_acc_001` reached the frozen P6 planner but the Ollama request returned `ReadTimeout` after
approximately 600 seconds. No grounding, `AdaptiveRouteDecision`, candidate SQL or execution was
produced. The wrapper removed that infrastructure terminal and performed its single permitted
retry against the same checkpoint; the retry ended at the same planner timeout. Full Olist and
Spider were therefore not started.

The progress file mechanically contains one `MODEL_ERROR` and zero correct results. This is not an
accepted `0/1` accuracy observation because the architecture under test never reached its routing
boundary and emitted no SQL. The correct experimental status is infrastructure-inconclusive, not an
accuracy rejection or promotion.

Local uncommitted artifacts and hashes:

- `evals/predictions/olist-paper2-adaptive-e8fab80-v1.jsonl`:
  `264a1771a2ae3fa6afb3e717dc796ad3557f462d62ab0ad1349d9cb03cb7e751`;
- `evals/reports/olist-paper2-adaptive-e8fab80-v1.progress.json`:
  `32c4f6ba17f2f807ec566708ceca4c607349694ce2b84e13f2da89e16fc287c5`.

Observed pilot peaks were 1.843 GiB system RAM used, zero swap, 1,682 MiB VRAM, 56 C, 45.07 W and
600 MHz. No resource threshold, OOM or shutdown occurred. After stopping, all model/benchmark
processes were absent; the verified idle sample showed 22 GiB available RAM, zero swap, 688 MiB
VRAM, 50 C, 20.95 W and a reset 210 MHz clock.

The one-layer safety profile is too slow to evaluate the restored P6 planner within the fixed
600-second request deadline. The same run must not be retried a third time or silently resumed.
Accuracy evaluation requires the unchanged frozen revision on a sufficiently capable server, or a
separately calibrated and explicitly approved laptop profile with a new one-case pilot and a fresh
evaluation ID. Until then R2 remains `IN_PROGRESS` and P6 remains champion.
