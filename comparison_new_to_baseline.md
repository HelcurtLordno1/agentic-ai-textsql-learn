# Paper I / PRACTIQ architecture compared with the frozen Olist baseline

**Experiment status:** stopped by the predeclared accuracy kill criterion

**Date:** 2026-09-03 (Asia/Bangkok)

**Decision:** **REJECT the current integrated Paper-I variant as the Olist champion.** Retain the
question-reliability work as an experimental feature, but do not replace the frozen P6 baseline.

## 1. Executive conclusion

The frozen baseline completed Olist-60 with **57/60 result-correct (95.00%)**. The new architecture
was stopped after case 35 because it already had five result-level failures. Even if every remaining
case 36--60 were correct, its maximum possible final score would be only **55/60 (91.67%)**. It is
therefore mathematically impossible for this run to equal or beat the baseline.

This conclusion does not treat a successful SQL execution as correctness. The stopped prefix was
evaluated offline against the reviewed gold results: **30/35 (85.71%)**. On the same first 35 cases,
the baseline was **33/35 (94.29%)**, a paired regression of **3 cases / 8.57 percentage points**.

The new architecture fixed two baseline errors in this paired prefix (`olist_acc_014` and
`olist_acc_023`), but introduced five different regressions (`olist_acc_021`, `027`, `029`, `031`,
and `035`). Net paired change: **+2 fixes, -5 regressions = -3 correct cases**.

The experiment is incomplete by design after the kill criterion: no measured 60-case score, holdout
score, or `60/60 workflow completion` is claimed. The defensible full-suite statement is the upper
bound **at most 55/60**, which is already below 57/60.

## 2. Compared systems

Both runs use the reviewed `olist-acceptance-60.jsonl`, Olist SQLite built by the project, local
Qwen3-14B Q4_K_M, deterministic seed 42, gold-blind runtime, and an evaluator that opens gold only
after prediction. Runtime code does not import the evaluator or benchmark gold.

### Frozen P6 baseline

```text
Question
  -> router/decomposer
  -> one-shot logical planner
  -> hybrid schema retrieval and context packing
  -> one SQL candidate
  -> AST/read-only/semantic/result validation
  -> bounded correction when eligible
  -> typed result
```

The baseline does not have an authoritative schema-aware `ANSWER / CLARIFY / CANNOT_ANSWER`
decision before SQL generation. It relies on the existing router, planning, grounding, validation,
and correction path.

### Paper-I / PRACTIQ-inspired variant

```text
RawQuestion
  -> lossless QuestionNormalizer (VI/EN, typo and diacriticless aliases)
  -> rule-first safety/unsupported checks
  -> schema- and glossary-aware QuestionAnalyst
  -> Interpretation(metric, dimensions, filters, grain, assumptions)
  -> authoritative AnswerabilityDecision
       ANSWER          -> planner/grounding/generation/validation/correction
       CLARIFY         -> typed clarification and 2--3 business choices
       CANNOT_ANSWER   -> typed missing-evidence response
       SAFE_REJECT     -> typed policy refusal
```

Additional integration work in the new path:

- accepted interpretation concepts survive scalar-plan normalization and feed retrieval;
- deterministic Olist status questions bypass unnecessary ambiguity analysis;
- physical-only ambiguities may collapse to one business interpretation;
- schema linking scores exact dimensions, raw aggregate measures, and base entity ownership;
- semantic validation checks full distributions, exact status filters, scalar aggregates, review
  row grain, customer identity, late delivery, payment/item grain, and tie-breaks;
- API/CLI/UI contracts can return clarification and continue bounded conversation state;
- local-LLM execution uses guarded batch size 1, explicit one-layer GPU offload, unloads, cooldown,
  continuous sensors, and a hard graphics-clock cap.

This follows PRACTIQ's useful product boundary—decide whether SQL should be generated before doing
so—but does not import PRACTIQ code or gold data into runtime.

## 3. Reproducible evidence

| Evidence | Baseline | New variant |
|---|---:|---:|
| Evaluation ID | `olist-acceptance-60-p6-v1` | `olist-paper1-r1-60-v3-stopped` |
| Evaluated cases | 60 | 35-case stopped prefix |
| Result correct | 57/60 (95.00%) | 30/35 (85.71%) |
| Same first-35 slice | 33/35 (94.29%) | 30/35 (85.71%) |
| First-pass correct | 51/60 (85.00%) | 30/35 (85.71%) |
| Correction attempted/recovered | 6/6 | 0/0 |
| P50 latency | 61.92 s | 193.27 s |
| P95 latency | 91.62 s | 259.18 s |
| English | 28/30 (93.33%) | 17/17 (100%) on prefix |
| Vietnamese | 29/30 (96.67%) | 13/18 (72.22%) on prefix |
| Dev | 28/30 (93.33%) | 27/30 (90.00%) |
| Regression | 14/15 (93.33%) | 3/5 (60.00%) on observed prefix |
| Holdout | 15/15 (100%) | Not run; no claim |
| Full-suite upper bound | 57/60 measured | **<=55/60**, because 5 failures are fixed in denominator |

Latency is not an architecture-only A/B. The safe new run used one GPU layer and a 300--600 MHz
hard clock cap after the earlier laptop shutdown/power breach, whereas the historical baseline used
six GPU layers and reported a 91.75 W peak. The new latency is valid operational evidence for the
safe profile, but must not be presented as a controlled estimate of PRACTIQ overhead alone.

Artifacts and immutable identities:

- baseline report: `evals/reports/olist-p6-60.json`;
- stopped prediction prefix: `evals/predictions/olist-paper1-r1-60-v3.jsonl`;
- v3 provenance/source hashes: `evals/predictions/olist-paper1-r1-60-v3.provenance.json`;
- offline prefix report: `evals/reports/olist-paper1-r1-prefix35-v3.json`;
- prediction SHA-256 at stop:
  `338498882dbde8b8bf91295cc2f5584a80f73cc9b26f98eddd4a6d23fda02e0a`;
- provenance SHA-256:
  `650f372656c103b1ab0d959b0b82f0eebcafe34e031b2292ce3b14a83f85ad35`;
- prefix report SHA-256:
  `7d857a4e683134c8c320cc765529a4cb0351ed06f8a06b18c9c7b4d4455712c7`.

## 4. Exact new-architecture failures

### `olist_acc_021` — wrong physical relation, silently wrong result

- Question: `Có bao nhiêu sản phẩm thiếu danh mục?`
- Expected: `610` products from `olist_products_dataset` with null category.
- Generated SQL:

```sql
SELECT COUNT(*)
FROM product_category_name_translation
WHERE product_category_name IS NULL
```

- Actual: `0`; status was `SUCCEEDED`.
- Cause: the physical-only ambiguity collapse accepted the business meaning, but grounding then
  selected the translation lookup rather than the product population. This demonstrates why
  answerability and schema ownership must be separate contracts: collapsing a user-irrelevant table
  choice is correct only if the linker can still guarantee the metric population.

### `olist_acc_027` — valid MAX rejected by an over-broad ranking rule

- Question: maximum payment-row value in cents.
- Expected: `1366408`.
- Generated SQL was semantically correct:

```sql
SELECT MAX(payment_value_cents) AS max_payment_value_cents
FROM olist_order_payments_dataset
```

- Status: `VALIDATION_FAILED`, `SEMANTIC_MISMATCH`; no result returned.
- Cause: Vietnamese superlative wording was treated as a ranked-row request even though the question
  asks for a scalar maximum. Planner/validator alignment remains incomplete across languages.

### `olist_acc_029` — correct idea, validator reports derived-column scope incorrectly

- Question: average item count per order, rounded to four decimals.
- Expected: `1.1417`.
- Generated SQL:

```sql
SELECT ROUND(AVG(item_count), 4) AS avg_items_per_order
FROM (
  SELECT COUNT(*) AS item_count
  FROM olist_order_items_dataset
  GROUP BY order_id
)
```

- Status: `EXECUTION_ERROR`, `UNKNOWN_COLUMN`.
- Cause: the SQL expresses the intended derived aggregate, but static schema validation does not
  resolve the subquery alias `item_count`. The existing `order_item_totals` semantic view would also
  have avoided the derived-column validation gap.

### `olist_acc_031` — scalar maximum converted into grouped top-one

- Question: maximum order count for one `customer_unique_id`.
- Expected: `17`.
- Generated SQL:

```sql
SELECT COUNT(*) AS order_count
FROM olist_orders_dataset
GROUP BY customer_id
ORDER BY order_count DESC
LIMIT 1
```

- Status: `VALIDATION_FAILED`, `SEMANTIC_MISMATCH`.
- Cause: the accepted interpretation did not force the reviewed identity/grain contract
  (`customer_unique_id`, `customer_order_facts.order_count`) strongly enough. It also repeats the
  known distinction between order-scoped `customer_id` and real-customer `customer_unique_id`.

### `olist_acc_035` — hard join omits the product table

- Question: top five English product categories by item revenue with deterministic tie-break.
- Expected top rows begin with `health_beauty`, `watches_gifts`, `bed_bath_table`,
  `sports_leisure`, and `computers_accessories`.
- Generated SQL joined item rows directly to the translation table through a nonexistent
  `oi.product_category_name` column.
- Status: `EXECUTION_ERROR`, `UNKNOWN_COLUMN`.
- Cause: grounding/generation omitted the required bridge
  `order_items.product_id -> products.product_id -> translation.product_category_name`. The current
  exact-dimension preference is insufficient for multi-hop hard joins.

## 5. Paired transitions versus baseline

Improvements on the same prefix:

- `olist_acc_014`: full order-status distribution no longer receives an accidental `LIMIT 1`.
- `olist_acc_023`: distinct customer states no longer become distinct customer identities.

Regressions on cases the baseline got right:

- `olist_acc_021`, `olist_acc_027`, `olist_acc_029`, `olist_acc_031`, `olist_acc_035`.

There were no cases wrong in both systems within the first 35. Consequently, the new architecture
changed behavior materially, but its improvements did not compensate for new planner/linker/
validator failures.

The baseline's third full-suite failure, `olist_acc_038`, lies outside the stopped prefix. It passed
an earlier isolated diagnostic after the new status/timestamp fix, but that diagnostic is not counted
as v3 benchmark evidence and cannot be combined with this stopped run.

## 6. Safety record and stop decision

The resumed run used the approved `olist-paper1-ultrasafe` profile: Qwen3-14B with one GPU layer,
batch size 1, one loaded model, 0.5-second monitoring, model unload between cases, 60-second cooldown,
VRAM below 4 GiB, temperature below 65 C, 78 W stop, and a verified 300--600 MHz Administrator
graphics-clock lock. Generation and embedding models did not run concurrently.

The case-29 resume pilot peaked at 49.0 W, 59 C, 1,585 MiB VRAM, and zero swap. The continued segment
through case 35 peaked at 50.74 W, 59 C, 1,665 MiB VRAM, and zero swap. The guard did not breach.
After the accuracy stop, Ollama and all runners were stopped and `nvidia-smi.exe -rgc` completed with
Administrator exit code 0.

Stop logic:

1. At 35 predictions, four terminal failures already made the terminal-status upper bound 56/60.
2. Offline result evaluation then found a fifth error hidden behind `SUCCEEDED` (`olist_acc_021`).
3. Therefore the true upper bound became `30 observed correct + 25 unrun = 55/60`.
4. Continuing could not meet or equal the 57/60 champion and would spend hours of local compute for
   no promotion decision, so the requested kill criterion was satisfied.

## 7. Why an accuracy increase initially looked plausible

The original expectation was reasonable as a **hypothesis**, but it was stronger than the evidence
available at the time.

### 7.1 PRACTIQ addresses a real missing product boundary

The official paper starts from a valid limitation of conventional text-to-SQL evaluation: most
datasets assume that the question has one clear, answerable intent. PRACTIQ instead defines four
ambiguous and four unanswerable categories, builds roughly 2,800 conversations, and evaluates two
separate tasks: question-category classification and clarification-aware SQL prediction. Its
`classify -> clarify/help/refuse -> SQL` boundary therefore directly targets confident but unsafe
SQL on real chat input.

That suggested three credible improvements for this project:

1. refuse unsupported questions before hallucinating a table or column;
2. preserve explicit metric, dimension, filter, grain, and assumption concepts for the planner;
3. understand Vietnamese/English conversational commands, typos, missing diacritics, and follow-up
   clarification more consistently.

These are genuine reliability improvements. It was tempting—but not yet demonstrated—to infer that
better intent interpretation would also improve execution accuracy on clean Olist questions.

### 7.2 The proposed modules matched known baseline errors

The frozen baseline failed only `olist_acc_014`, `023`, and `038`. The new interpretation contract,
status handling, and stronger semantic checks were designed around exactly these error families.
They did fix `014` and `023` in the paired run, and an earlier isolated diagnostic passed `038`.
That local evidence made a score above 57/60 appear attainable.

However, those targeted reruns were development diagnostics, not an unbiased sample. They measured
whether known failures could be repaired, but did not measure how many already-correct cases the new
logic would disturb. This is a classic selection effect: testing only the three places with upside
cannot estimate the net change across the other 57 cases.

### 7.3 The initial mental model treated the analyst as a safe additive layer

The intended abstraction was:

```text
better interpretation -> same proven SQL pipeline with better inputs -> equal or better accuracy
```

The implemented system was materially different:

```text
analyst output
  -> changes concepts and assumptions
  -> changes retrieval candidates and schema ownership
  -> changes the logical plan
  -> changes generated SQL
  -> triggers new semantic-validator branches
  -> shares one deadline with correction
```

The analyst is therefore not a passive guard. Once authoritative, it changes several downstream
distributions and can create new failures even when its natural-language interpretation is correct.

### 7.4 Paper results did not establish this particular transfer

PRACTIQ demonstrates that ambiguous/unanswerable detection and clarified SQL are important and hard.
It does **not** report that inserting one extra prompt call into an already strong, local Olist
pipeline monotonically improves clean-answerable execution accuracy. The paper's limitation section
states that the authors did not fine-tune open-source models with the generated data because of time
constraints and left that experiment for future work. The reported framework and dataset are thus
research support for the reliability objective, not a plug-and-play accuracy guarantee for a
Qwen3-14B prompt-only integration.

## 8. Why measured accuracy decreased

The regression is best explained as a causal chain rather than one bad model response.

### 8.1 The optimization target and the benchmark target differ

Olist-60 contains clean, answerable requests whose expected outcome is SQL. It gives no positive
credit for correctly clarifying an ambiguous request or refusing an unanswerable request. PRACTIQ's
main additional capability therefore has almost no upside available on this distribution, while its
extra classification, interpretation, retrieval, and validation decisions remain active.

In statistical terms, the new architecture changed the task mixture it was optimized for, but the
promotion gate measured only the old answerable-SQL slice. A model can improve practical risk—fewer
confidently wrong answers on messy chat—and still lose clean execution accuracy. Both statements can
be true; the current experiment directly proves only the second one for this implementation.

### 8.2 A 95% baseline leaves almost no regression budget

At 57/60, only three baseline errors were available to fix. A result of 58/60 required at least one
net recovery across the whole suite. The paired prefix produced:

```text
2 baseline failures repaired
- 5 previously correct cases regressed
= net -3 correct cases on the first 35
```

Even a generally sensible heuristic is unacceptable at this ceiling if it repairs one narrow case
but destabilizes two correct ones. The needed changes had to be surgical and monotonic; the new
cross-cutting rules were neither.

### 8.3 Error compounds across stages

| Case | Analyst/plan signal | Downstream break | Observable consequence |
|---|---|---|---|
| `021` | Correctly interpreted “products missing category” | linker chose the translation lookup as the population | executable but silently wrong `0` instead of `610` |
| `027` | Correct scalar `MAX(payment_value_cents)` SQL | broad superlative/ranking validation rejected scalar maximum | false-positive `SEMANTIC_MISMATCH` |
| `029` | Correct average-of-per-order-count idea | validator could not resolve derived alias `item_count` | false `UNKNOWN_COLUMN`; semantic view was not selected |
| `031` | Analyst named `customer_order_facts` and `customer_unique_id` | later ownership heuristic reverted to raw customer/order tables | wrong identity and grouped top-one instead of scalar maximum |
| `035` | Correct product-revenue/English-category intent | exact-dimension preference selected translation without join closure | missing products bridge and nonexistent item column |

This table is important: in several cases the LLM's business interpretation was correct. Accuracy
fell because semantic information was weakened, overridden, or misvalidated between contracts.
Increasing the amount of reasoning did not ensure that the decisive physical schema constraints
survived to generation.

### 8.4 The new call consumed the correction budget

Four failures were returned as validation/execution errors but received no correction attempt:

| Case | Total latency | Answerability call | Correction outcome |
|---|---:|---:|---|
| `027` | 193.2 s | 103.9 s | not attempted; `DEADLINE` |
| `029` | 153.5 s | 84.3 s | not attempted; `DEADLINE` |
| `031` | 143.5 s | 78.9 s | not attempted; `DEADLINE` |
| `035` | 174.8 s | 101.4 s | not attempted; `DEADLINE` |

By contrast, the frozen baseline attempted six corrections and recovered all six. The authoritative
answerability call used roughly half or more of the per-case time in these traces, leaving the shared
deadline exhausted precisely when the bounded repair loop was needed. Thus the architecture added a
new reasoning stage but effectively removed a previously high-value recovery stage on hard cases.

This does not prove the extra call alone caused every error. The historical baseline used six GPU
layers, while the safe run used one layer plus a 300--600 MHz clock cap, so the latency numbers are
not a controlled architecture-only A/B. The trace-level `DEADLINE` stops do prove that under the
required safe deployment profile the present deadline allocation is operationally incompatible with
correction.

### 8.5 Local heuristics had non-monotonic interactions

The modifications solved particular examples but generalized too broadly:

- exact-dimension ownership helps a simple lookup, but in `035` it selects the dimension table
  without ensuring a complete fact-to-dimension join path;
- collapsing “physical-only” ambiguity avoids unnecessary questions, but in `021` it removes the
  safety pause without proving which relation owns the counted population;
- base-entity ownership can help direct counts, but in `029` and `031` it displaces reviewed semantic
  views that already encode the required grain;
- a superlative guard catches unsafe `ORDER BY ... LIMIT 1`, but in `027` it also rejects a legitimate
  scalar `MAX`.

These are interaction failures between rules, not evidence that the individual principles are
wrong. They show that each rule needs a typed precondition and an invariant test, rather than a
global score bonus or keyword match.

### 8.6 Workflow success was confused with result correctness

`olist_acc_021` ended as `SUCCEEDED` because its SQL was valid and executable. Only offline result
comparison exposed that it counted the wrong relation. Monitoring only terminal status would have
reported four failures instead of five and overstated the upper bound as 56/60. For research claims,
execution success is therefore a pipeline-health metric, not an accuracy metric.

## 9. Causal verdict

The most defensible explanation is:

```text
PRACTIQ objective is useful
  + implementation activated it on an all-answerable suite
  + authoritative concepts altered a mature 95% pipeline
  + broad heuristics displaced population/grain/join invariants
  + the extra LLM call exhausted correction time on hard cases
  = two intended fixes but five new regressions
```

The result does **not** justify “PRACTIQ lowers text-to-SQL accuracy.” It supports the narrower claim
that this prompt-only, always-on integration of PRACTIQ-inspired decision logic lowered clean Olist
accuracy under the laptop-safe Qwen3-14B runtime. The distinction matters because the experiment did
not yet score the ambiguous/unanswerable distribution that the paper was designed to improve.

## 10. Threats to validity

- **Stopped suite:** the new run has measured results only for cases 1--35. The 55/60 figure is a
  mathematical upper bound, not a completed accuracy measurement.
- **Hardware confound:** GPU-layer and clock settings differ between the historical baseline and new
  run. They directly affect latency and correction opportunity; they are not evidence of semantic
  inferiority by themselves.
- **Prompt/model stochasticity:** the model and seed are fixed, but local LLM generation is not a
  proof of bit-identical outputs across runtime versions and hardware schedules.
- **Development selection:** isolated reruns of known failures encouraged optimism and must not be
  combined with the fresh benchmark as if they were held-out observations.
- **Metric mismatch:** Olist execution accuracy cannot quantify clarification quality, false refusal,
  unanswerable detection, or reduced confident-wrong risk.
- **Small paired difference:** the paired prefix establishes the exact result for these 35 cases but
  is too small to support a universal claim about all schemas, languages, or models.

## 11. GitHub audit: exact frozen-baseline commits

The configured `origin` is the requested repository
`https://github.com/HelcurtLordno1/agentic-ai-textsql-learn.git`. A read-only
`git ls-remote origin refs/heads/main` on 2026-09-04 returned
`cebfeb1fd1499c0fcb7f88634b594e2bf9b5135e`, equal to local `origin/main` and `HEAD`. No fetch,
checkout, commit, or push was performed.

There are two baseline dates because **the code snapshot** and **the commit that records its benchmark
evidence** are consecutive but distinct commits:

| Meaning | Commit | Time (UTC+07) | Evidence |
|---|---|---|---|
| Frozen baseline execution/code revision | [`1509faa786534f36d33df34d4d5c4a9ed5fc1c54`](https://github.com/HelcurtLordno1/agentic-ai-textsql-learn/commit/1509faa786534f36d33df34d4d5c4a9ed5fc1c54) | 2026-08-14 17:03:45 | `feat: define laptop-stratified Gate P6 benchmark`; the current research plan identifies this as the historical baseline revision |
| Commit that records/verifies 57/60 | [`0972e4715f2aa8a64652c3b27d10c80f178bc162`](https://github.com/HelcurtLordno1/agentic-ai-textsql-learn/commit/0972e4715f2aa8a64652c3b27d10c80f178bc162) | 2026-08-14 22:27:54 | `docs: verify Gate P6 laptop release`; adds `docs/evidence/p6_gate.md`, which records Olist 57/60 and Spider 130/200 |
| Current remote `main`, not the clean baseline snapshot | [`cebfeb1fd1499c0fcb7f88634b594e2bf9b5135e`](https://github.com/HelcurtLordno1/agentic-ai-textsql-learn/commit/cebfeb1fd1499c0fcb7f88634b594e2bf9b5135e) | 2026-09-03 08:47:51 | `feat: add guarded reliability workflow and hardware runbook` |

Git ancestry confirms that `0972e47` is the direct child of `1509faa`. The diff between them changes
documentation/evidence assets and the completion ledger, not runtime source code. Therefore the
precise citation for future experiments is:

> **Baseline system revision:** `1509faa`; **baseline result evidence commit:** `0972e47`; **verified
> Olist result:** 57/60 (95.00%), recorded on 2026-08-14.

Using only `0972e47` as “the model code commit” would blur provenance; using only `1509faa` would omit
where the excellent score was actually recorded. The current `main` commit `cebfeb1` must not be
described as the frozen champion because it already contains later reliability workflow changes.

## 12. Revised architecture and experiment recommendation

1. Keep P6 (`57/60`) as champion and keep `R1-M1` unverified.
2. Make the PRACTIQ gate conditional. Use a cheap deterministic fast path for demonstrably clean,
   answerable requests and invoke the LLM analyst only when ambiguity/unsupported evidence exists.
3. Make `Interpretation` constraints mandatory downstream invariants: population owner, business
   identity, grain, scalar-versus-ranking form, and a closed join path must survive planning and
   schema linking or fail closed.
4. Reserve correction time before starting answerability—for example, separate bounded stage budgets
   rather than one shared deadline. Preserve laptop guards; do not solve latency by loosening thermal,
   RAM, VRAM, or power limits.
5. Replace global keyword/score heuristics with typed predicates and add deterministic regression
   tests for the five exact failure mechanisms without importing benchmark gold into runtime.
6. Evaluate two axes independently:
   - Olist clean-answerable no-regression: fresh 60/60 run, at least 57/60 and preferably 58/60;
   - PRACTIQ-style reliability: macro-F1 by category, false-refusal rate, clarification success,
     unsupported-query recall, and confident-wrong rate.
7. Use a fresh evaluation ID, immutable source/config hashes, and a new prediction file after every
   code change. Never splice the stopped v3 prefix into a changed implementation.

This design tests the actual research proposition: reliability should improve on messy conversational
inputs **without** sacrificing the frozen clean-answerable champion.

## 13. Claim boundary

- Proven: current v3 cannot exceed 55/60 and is therefore worse than the 57/60 baseline.
- Measured: new prefix 30/35 versus paired baseline prefix 33/35.
- Not measured: new cases 36--60, new holdout accuracy, or a full v3 latency distribution.
- Not claimed: Paper I generally reduces SQL accuracy, or that safe clarification has no value.
- Gate status: the current Olist Paper-I variant is **REJECTED for promotion**; `R1-M1` must not be
  marked `VERIFIED` from this evidence.

## 14. Repository verification after the stop

The required repository check completed after the report and ledger updates: Ruff passed, all 227
files passed the formatting check, strict mypy completed for the source tree, and the non-Ollama test
suite passed **221 tests** with one Ollama-marked test deselected. The only emitted warning was the
existing Starlette/httpx test-client deprecation warning. No benchmark or local model was running
during these checks.

## 15. External research sources

- Dong et al., [PRACTIQ: A Practical Conversational Text-to-SQL Dataset with Ambiguous and
  Unanswerable Queries](https://aclanthology.org/2025.naacl-long.13/), NAACL 2025,
  DOI `10.18653/v1/2025.naacl-long.13`.
- The GitHub commit links in Section 11 are the public audit trail for the baseline revision,
  evidence commit, and current remote `main`. Local Git objects and the remote branch hash were also
  checked so that a search-engine timestamp was not used as provenance.
