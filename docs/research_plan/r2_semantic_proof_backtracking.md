# R2 semantic proof, failure-directed backtracking, and Olist protocol

**Status (2026-09-13):** Revision G clean prefix reached 7/10 and was rejected. Its code is archived
at `c4851eb`; Revision E 28/31 was restored at `80e94ec` and passes `make check` with 260 non-Ollama
tests. R2 remains `IN_PROGRESS`, not `VERIFIED`. This document is architecture provenance, not a
benchmark prompt or runtime input.

## Research claim being tested

The working hypothesis is narrower than “more agents improve Text-to-SQL.” Accuracy should improve
when the system identifies entity, skeleton, value, and grain failures separately; converts
high-confidence business semantics into typed, catalog-validated proof obligations; and repairs
only failed clauses under a bounded execution loop. SQLens motivates clause-level semantic signals
from database and model evidence [1]. Multi-grained Error Identification motivates the
system/skeleton/value taxonomy [2]. DAC motivates comparing decomposed entities and skeletons
instead of asking an LLM to judge opaque SQL directly [3]. DART-SQL motivates database-aware,
execution-guided refinement [4].

This project independently implements those ideas for a local laptop budget. It does not claim an
exact reproduction of any paper, reuse their code, or transfer their published gains to Olist.

## Paper-to-architecture mapping

| Research idea | Local implementation | Falsifiable evidence |
|---|---|---|
| SQLens clause-level errors [1] | `semantic_checks.py` emits named signals for population, grain, aggregate, filter, order and limit contradictions | tests require rejection and a valid counterexample |
| Multi-grained errors [2] | policy/execution cover system errors; typed plan/AST checks cover skeleton; catalog predicates cover value; this project adds grain | artifacts record class, signals, attempts and stop reason |
| DAC entity/skeleton comparison [3] | `SemanticBinding`, `ClausePlan`, `validate_plan`, and original-SQL validation compare intent with SQL before correction | tampered binding, owner and clause tests fail closed |
| DART-SQL refinement [4] | every repair re-enters policy, read-only execution, result-shape and semantic checks | at most two repairs/calls plus repeated SQL/error/deadline stops |
| Laptop extension | proven bindings bypass DIN planner/generator and compile deterministically | compiler provenance and LLM-call count are recorded |

## Revision D evidence and failure decomposition

Evaluation `olist-r2d-proof-fastpath-v1` used the approved `olist-paper1-ultrasafe` wrapper with one
GPU layer, batch size one, unload after every batch, 0.5-second sampling and 60-second cooldown. The
Administrator clock lock was active at 300--600 MHz. The predeclared accuracy upper bound stopped
the run at 31 cases: 28 correct, so the maximum final score was 57/60, below target 58/60. Holdout
cases 46--60 were never run or inspected.

- prediction SHA-256: `a8cbca3a2d825227f70d127e6aaf273a7ead23cae095df3522203e1ca8932df9`;
- progress SHA-256: `b219cecc1b3d31a44b54239aa626d1145511ec54a941027155e3db8d2a7cc403`;
- peak VRAM 1,755 MiB, 57 C, 55.74 W, 600 MHz, swap 0;
- after stop: no model/benchmark process, 673 MiB VRAM, 51 C and 18.15 W.

Only failures 25 and 29 (development) and 31 (regression) were inspected after the suite stopped.
They expose three general causes:

1. A raw review-frequency question selected an order-summary view: entity existed, but population
   grain and deterministic tie-break were wrong.
2. A valid derived-table alias was rejected as an unknown catalog column: a policy system error,
   not a database execution error.
3. Maximum orders were grouped by `customer_id`; the requested stable identity was
   `customer_unique_id`, whose correct one-row-per-customer view already existed.

## Revision E design

Revision E adds no benchmark ID or gold SQL to runtime. It introduces reusable contracts:

- scope-aware identifier validation resolves base-table, CTE and derived-table exports while still
  rejecting invented local or projected columns;
- `FrequencyRankingSpec` proves one-table grouped row frequency, count-descending order, bounded
  limit and deterministic ascending dimension tie-break;
- semantic catalog aliases resolve average items per order and maximum order count at
  `customer_unique_id` grain;
- adaptive routing activates on explicit frequency ranking, average-per-group, and grouped scalar
  maximum dependencies;
- `generator_v8_proof_compiler` compiles all three proven shapes without a DIN planner/generator
  call; correction remains a bounded fallback when proof is incomplete.

Construction evidence: `make check` passed Ruff, formatting, mypy on 111 source files, and 266
non-Ollama tests (one Ollama test deselected). The clean run reached 28/31; its maximum possible
score was 57/60, so the upper-bound gate stopped it before holdout. Cases 25 and 29 were recovered;
case 20 still used the wrong payment population, case 30 timed out in grounded planning, and case
31 produced correct SQL but was rejected by an over-broad identity check.

## Revisions F--G: rejected typed completion and global proof-first control

Revision F added a payment-frequency rule at raw payment-record grain, a freight-per-order alias
with typed rounding, and lineage-aware validation for a proven `customer_unique_id` source grain.
It also moved explicit complex dependencies ahead of planner v2. `make check` passed 270 non-Ollama
tests. Its first pilot was infrastructure-inconclusive: case 1 timed out twice in planner v2 after
240 seconds, with safe peaks below 2,125 MiB VRAM, 56 C and 45.18 W. No content result from that
pilot is treated as accuracy evidence, and its checkpoint will not be resumed.

Revision G generalizes the proof gate without adding benchmark-specific logic. Before retrieval or
an LLM call, the runtime attempts an exact semantic binding against the schema-validated catalog.
A complete one-owner proof creates a minimal `SchemaContext`, a typed DIN plan and compiled SQL.
Incomplete or ambiguous bindings fall back to explicit-complex DIN routing or the frozen P6
planner/generator path. This turns the architecture into a bounded evidence hierarchy:

```text
exact catalog proof -> typed plan -> deterministic compiler
          | incomplete / ambiguous
          v
explicit dependency -> grounded DIN model path
          | absent
          v
frozen P6 planner -> grounding -> baseline generator/corrector
```

The fast path never invokes BM25/dense retrieval, BGE or Qwen; catalog hash, source grain, owner,
columns and clause contracts are still validated before read-only execution. This is the local
implementation of clause/grain proof suggested by SQLens and DAC, with fail-closed backtracking
rather than model self-confidence. `make check` passes 271 non-Ollama tests (one Ollama test
deselected), including a forbidden-retriever test and a zero-model-call integration test.

The clean Revision G run falsified this integration: it reached only 7/10, with 8/10 questions
routed through the proof path. Alias-level catalog matches were not sufficient proof of the whole
question's population, grain and output contract. Revision G is therefore archived, not promoted;
the live research checkpoint was restored to Revision E. Exact payment/freight phrases and
post-failure product-category checks were removed rather than retained as benchmark-shaped rules.

## Locked evaluation protocol

1. Confirm no stale jobs and safe idle RAM, swap, VRAM, temperature, power and clock.
2. Verify the existing OS 300--600 MHz cap; never infer it from configuration alone.
3. Start the guarded Ollama server with `olist-paper1-ultrasafe` and explicit one-layer GPU offload.
4. Run a fresh one-case pilot with a new evaluation ID and artifact paths.
5. Continue only the exact pilot checkpoint if every sample remains under the profile thresholds.
6. Score offline after each durable prediction and stop once 58/60 becomes impossible.
7. Do not inspect predictions during the run. Development/regression failures may inform another
   revision only after stop; holdout failures may be reported but never tuned.
8. Stop/unload Ollama, verify idle state, hash artifacts, rerun `make check`, and update the ledger.

Spider remains downstream of Olist. It becomes scientifically useful only after the small-domain
semantic contracts are stable enough to beat the frozen 57/60 Olist baseline; otherwise Spider can
hide basic grain/validator faults behind a larger aggregate score.

## Sources

1. [SQLens: An End-to-End Framework for Error Detection and Correction in Text-to-SQL (NeurIPS 2025)](https://proceedings.neurips.cc/paper_files/paper/2025/hash/c57812dee8acade8c5e385260b2cde28-Abstract-Conference.html)
2. [Boosting Text-to-SQL through Multi-grained Error Identification (COLING 2025)](https://aclanthology.org/2025.coling-main.289/)
3. [DAC: Decomposed Automation Correction for Text-to-SQL (Findings of EMNLP 2025)](https://aclanthology.org/2025.findings-emnlp.22/)
4. [DART-SQL: Enhancing Text-to-SQL Parsing through Question Rewriting and Execution-Guided Refinement (Findings of ACL 2024)](https://aclanthology.org/2024.findings-acl.120/)
