# R1 question reliability — implementation evidence

Status: `IN_PROGRESS` (code/test boundary complete; experiment promotion is not claimed)
Paper mechanism: Dong et al., [PRACTIQ](https://aclanthology.org/2025.naacl-long.13/), NAACL 2025
Implementation date: 2026-08-31

## Implemented boundary

```text
raw question
  → lossless Unicode/VI-EN normalization
  → deterministic write, unsupported-request, and Olist missing-fact rules
  → one schema-constrained local question-analyst call
  → ANSWER | CLARIFY | CANNOT_ANSWER | SAFE_REJECT
       └─ SQL planning/generation is reachable only from ANSWER
```

The implementation transfers PRACTIQ's pre-SQL category decision and four-turn clarification
contract. It does not copy PRACTIQ data/code into runtime, add a paid provider, expose database rows,
or use benchmark gold. The question analyst receives bounded schema and declared-FK metadata only.
Database-value evidence remains a later CHESS boundary.

Implemented components:

- frozen typed `NormalizedQuestion`, `Interpretation`, `AnswerabilityDecision`, and
  `ClarificationContext` contracts;
- raw-preserving NFKC normalization, no-diacritic search text, conservative VI/EN aliases and common
  typo repair;
- PRACTIQ nine-way schema-aware prediction mapped to product outcomes;
- deterministic safe rules and fail-closed malformed-output behavior;
- early exits with no planner, generator, execution, or correction call;
- exactly one accepted interpretation passed to the existing planner on `ANSWER`;
- persisted `parent_run_id`, API/CLI follow-up input, and UI business choices;
- gold-isolated macro-F1, ambiguity-recall, false-refusal, and clarification-success metrics;
- tracked 100-case paired-family pilot contract at
  `evals/configs/practiq-r1-challenge-families.yaml` (40 `ANSWER`, 30 `CLARIFY`, 30
  `CANNOT_ANSWER`; project-authored, single-reviewer).
- bounded Olist business glossary supplied to the analyst so physical table/grain alternatives do
  not become false business ambiguity;
- an ultra-safe guarded runner which checkpoints every case and stops both client and server on a
  RAM, swap, VRAM, GPU-temperature, or GPU-power breach.

## Reproducible checks

```bash
uv run pytest -q \
  tests/unit/layer1/test_question_reliability.py \
  tests/integration/test_question_reliability_gate.py \
  tests/unit/layer6/test_application_service.py \
  tests/integration/test_p5_api.py
uv run pytest -m "not ollama" -q
make check
```

Observed on 2026-08-31 after the final code changes:

- latest `make check`: Ruff pass, format pass, strict mypy pass for 110 source files, and
  216 tests passed with 1 Ollama test deselected;
- targeted reliability/application/metric suite: 17 passed;
- ambiguity integration test proves one analyst call and zero downstream model calls;
- answerable integration test proves analyst → planner → generator → read-only execution;
- API follow-up test proves the child run persists its parent and clarification context.

Live Olist pilot `7850d698-8f1e-4058-a2b0-3aa7bd1f0a49` answered the bilingual delivered-order
question with the grounded SQL predicate `order_status = 'delivered'` and result `96,478`, matching
the independently computed status count. This fixed an observed pre-change semantic error where a
delivery timestamp and later a translated Vietnamese literal were used instead.

The project-authored classification pilots are checkpointed but incomplete:

| Snapshot | Completed | Correct | Prefix accuracy | Purpose |
|---|---:|---:|---:|---|
| v3 | 31/100 | 23 | 74.19% | Located false clarification on explicit metrics |
| v4 | 40/100 | 37 | 92.50% | Verified glossary/prompt improvement |
| v5 | 22/100 | 22 | 100.00% | Final source snapshot before guarded stop |

These prefix accuracies are diagnostic only. They are not macro-F1, do not contain all three classes,
and must not be reported as final benchmark accuracy. The v5 prediction SHA-256 is
`1492efa8a942c3750f4b44e7b48283807a47780bc26e08fc1d1cfa58c00da9de`; its provenance records the
model digest, seed, challenge/database hashes, catalog hash, and source snapshot.

An unexpected laptop shutdown occurred while the former unguarded v5 runner was active. After reboot,
the new one-case ultra-safe pilot correctly stopped at a GPU-power breach of 72.02 W, with GPU 59 C,
2,274 MiB VRAM, at least 22.26 GiB available RAM, and zero swap. No case or checkpoint was lost and no
automatic retry was made. Full incident and recovery evidence is in
`docs/evidence/r1_resource_guard_incident.md`.

## Promotion blockers and honest claim boundary

Gate R0 is not complete. The challenge still lacks independent second-reviewer labels, and the guarded
v5 run stopped before reaching the `CLARIFY` and `CANNOT_ANSWER` partitions. Therefore:

- no final 100-case macro-F1 or new Spider/Olist suite accuracy is claimed;
- no `≥0.80` macro-F1, `≥85%` ambiguity recall, `≤3%` false-refusal, or `≥80%`
  clarification-success claim is made;
- no claim that confident-wrong decreased or end-to-end accuracy increased is made;
- `R1-M1` remains `IN_PROGRESS`, not `VERIFIED` or `PROMOTED`.

The next valid gate action is to obtain user approval for a safe hardware strategy that stays below
the current power circuit breaker, then resume v5 through the guarded runner. Promotion additionally
requires independent label review and completion of R0.
