# Gate R2 DIN-SQL implementation evidence

**Date:** 2026-09-06 (Asia/Bangkok)
**Status:** `IN_PROGRESS` — deterministic implementation complete; promotion benchmark pending

## Hypothesis and locked comparator

The locked comparator remains P6: Spider-200 `130/200` (65.00%) and Olist-60 `57/60` (95.00%).
Paper I/PRACTIQ is not a comparator champion: its source-locked run stopped at prefix 35 with
`30/35`, versus paired baseline `33/35`, and a full-suite upper bound of `55/60`.

The R2 hypothesis is that keeping schema ownership and SQL-clause dependencies as typed contracts
will reduce executable-but-semantically-wrong SQL, especially join/source, aggregation/grain and
nesting/set failures, without applying a long reasoning prompt to every easy query.

Primary research sources:

- Pourreza and Rafiei, *DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with
  Self-Correction*, NeurIPS 2023: [official paper](https://proceedings.neurips.cc/paper_files/paper/2023/file/72223cc66f63ca1aa59edaec1b3670e6-Paper-Conference.pdf)
  and [supplemental prompts](https://proceedings.neurips.cc/paper_files/paper/2023/file/72223cc66f63ca1aa59edaec1b3670e6-Supplemental-Conference.pdf).
- Internal transfer specification: `docs/paper_to_research_implement.md`, sections 4 and 9.
- Historical failures: `evals/failures/r0-historical-spider-200.json` and
  `comparison_new_to_baseline_vn.md`.

## Implemented interfaces

```text
DecomposedQuestion
  -> retrieval + compact connected schema closure
  -> SemanticLinkPlan
       mention, role, table/column owner, value, evidence_id, score
  -> deterministic schema-aware planner
  -> ComplexityDecision
       SIMPLE | AGGREGATE | MULTI_JOIN | NESTED_SET_WINDOW
       EASY | NON_NESTED | NESTED
  -> ClausePlan
       SELECT, FROM, JOIN, WHERE, GROUP, HAVING, ORDER, LIMIT,
       output grain, DISTINCT, set operation, ordered subquery dependencies
  -> deterministic PlanConsistencyValidator
  -> catalog-checked scalar EASY compiler, otherwise one strategy-specific SQL generation call
  -> normal Layer 4 execution/semantic validation
  -> optional one-shot clause-specific correction
```

The model returns only the draft, and runtime attaches the provenance-backed `SemanticLinkPlan`.
Unambiguous links and an exact raw-table `population_owner` are hard constraints; ambiguous physical
owners remain typed candidates so a more precise semantic view can replace them. Complexity is
recomputed from concrete clause structure instead of trusting the model's self-label. Validation
checks catalog identity, table/column owner, visible evidence, join endpoints/conditions/connectivity,
semantic population owner, scalar versus ranking shape, limits, complexity strategy and ordered
subquery dependencies.

Hybrid planning itself makes no generation-model request. A deliberately small compiler emits only
single-table scalar `COUNT`, `COUNT DISTINCT`, `SUM`, `AVG`, `MIN` or `MAX` queries plus catalog-
checked string equalities. It returns no candidate for any unsupported shape, identifier, join or
clause, causing the normal one-call generator path to take over. Embedding/schema retrieval occurs
before any generation-model request. Runtime has no import from `agentic_text2sql_eval` and no access
to gold data.

## Failure-directed protections

| Historical case/family | R2 protection |
|---|---|
| `olist_acc_021` wrong population table | An exact raw base entity becomes the required `population_owner`; ambiguous entity hints remain candidates. |
| `olist_acc_027` scalar maximum rejected as ranking | Scalar question alignment clears dimensions/order/limit; clause plan must have scalar grain. |
| `olist_acc_029` average items per order | Derived-average alignment forces a scalar outer result; nested steps carry their own clause contracts. |
| `olist_acc_031` customer identity/grain | Evidence owner and output grain survive into generator and correction prompts. |
| `olist_acc_035` missing product bridge | Join connectivity is validated; conservative `INFERRED_UNIQUE_LOOKUP` closes raw product-to-translation lookup only when one exact-name side is unique. |
| Spider executable semantic mismatch | Evaluator records clause F1, table/column/join recall and plan-to-SQL agreement separately from EX. |

An inferred lookup is not treated as an arbitrary same-name join. It is allowed only between two raw
tables with compatible exact-name columns, exactly one primary/unique side, and no already declared
FK between the table pair. Provenance labels it `INFERRED_UNIQUE_LOOKUP`; declared keys remain
`DECLARED_FK`.

## Reproducible deterministic evidence

Command:

```bash
make check
```

Observed result on 2026-09-06:

- Ruff lint: pass;
- Ruff format check: 224 files formatted;
- strict mypy: 108 source files pass;
- pytest excluding Ollama: 191 passed, 1 Ollama test deselected;
- one existing Starlette/httpx deprecation warning;
- no Ollama request, generation benchmark, embedding model, GPU workload or acceptance suite ran.

Focused coverage includes:

- `tests/unit/layer1/test_din_sql_planning.py`;
- `tests/unit/layer1/test_hybrid_failure_repairs.py`;
- `tests/unit/layer2/test_semantic_links.py`;
- `tests/unit/layer3/test_easy_compiler.py` (catalog-proven compilation and fail-closed fallback);
- `tests/integration/test_direct_baseline.py` (model-free EASY compilation, DIN hand-off and stop-before-generation failure);
- `tests/unit/test_din_sql_metrics.py`;
- existing Layer 4 safety and Layer 5 bounded-correction suites.

A read-only diagnostic against the locally built Olist catalog also resolved the case-035 seeds
`olist_order_items_dataset` and `product_category_name_translation` to exactly three tables via:

```text
olist_order_items_dataset.product_id = olist_products_dataset.product_id       [DECLARED_FK]
olist_products_dataset.product_category_name =
  product_category_name_translation.product_category_name                     [INFERRED_UNIQUE_LOOKUP]
```

This diagnostic inspected catalog metadata only; it did not start Ollama or execute benchmark
inference and is not accuracy evidence.

## Ablation and promotion contract

`TEXT2SQL_PLANNING_MODE=baseline|hybrid|din_sql` selects a source-recorded variant. Baseline mode uses
planner v2, generator v4 and corrector v3. DIN mode uses planner v3, generator v5 and corrector v4,
requires the active semantic index, and records plan validation in every result. Evaluators only
compute DIN planning metrics when the prediction actually contains a typed clause plan, so historical
reports remain readable.

After the all-DIN Olist run hit the predefined accuracy stop at 4/8 correct (upper bound 56/60), the
research implementation added a bounded hybrid route. Provable scalar EASY plans use a deterministic
catalog-checked compiler; unsupported EASY plans use the baseline generator and a compact
`LogicalPlan`; only validated `NON_NESTED`/`NESTED` plans use DIN generation. Plan validation
now separates blocking catalog/identifier violations from advisory shape/connectivity signals, which
fall back to the baseline generator. Deterministic regression tests cover status-value ownership,
scalar semantic-view ownership, distinct customer count without an unnecessary join, and seller
count grain. A first hybrid live snapshot passed `olist_acc_002`, then `olist_acc_005` reproduced a
600-second structured-generation `ReadTimeout` twice while all resource guards remained safe. That
artifact was stopped at 1/2 and retained as negative evidence. The EASY compiler removes that
unnecessary model boundary. A second source-locked smoke then passed cases 002 and 005, but case 007
showed that a retrieved identity column can carry the `METRIC` role rather than `DIMENSION`; the
planner consequently emitted `COUNT(*)` instead of `COUNT(DISTINCT customer_unique_id)`. That
artifact stopped at 2/3. Distinct-count planning now checks both roles inside the proven population
owner, and the live-shaped fixture passes.

The next four-case artifact completed `4/4` first-pass correct. A separate full-suite pilot then
found a broader Vietnamese count wording, “Có tổng cộng bao nhiêu đơn hàng?”, whose already-typed
`order count` metric was overridden by the lexical word “tổng” and compiled as `SUM(timestamp)`.
That full-suite artifact was stopped at `0/1`. Count intent now also derives from typed metric names
ending in `count`; amount questions such as “Tổng doanh thu ... là bao nhiêu?” remain `SUM`, covered
by both regressions. The next source-locked run passed cases 001–002, then exposed that Vietnamese
status literal “đã hủy” was sent verbatim to an English-valued `order_status` column. Status enum
aliases are now canonicalized (`đã hủy` → `canceled`, `giao thành công` → `delivered`) after mention
matching but before clause construction. The final source-locked Olist-60 run is still pending.

The implementation is deliberately **not VERIFIED** and no accuracy gain is claimed. Promotion still
requires the guarded, checkpointed paired experiment specified in the research plan:

- Spider overall +2 points or targeted medium/hard +3–5 points;
- easy and Olist regression inside guardrails;
- warm grounding p95 at most 1 second and zero leakage;
- DIN-SQL paper-specific target: medium+hard +5 points, overall +2 points, easy loses at most one
  case, end-to-end p95 increase at most 20%; kill if added plan length does not improve recoverability
  or propagates errors into easy cases.

Any local-model pilot/full run must use the guarded wrapper, batch size 1, continuous 0.5-second
resource monitoring, explicit bounded `TEXT2SQL_OLLAMA_NUM_GPU`, unload/cooldown/checkpointing and
the stop thresholds in `AGENTS.md`. This evidence intentionally stops before that separate gate.
