# Gate P2 evidence — 2026-08-06

## Implemented vertical slice

```text
Question
  -> deterministic Router
  -> deterministic clause Decomposer
  -> Qwen3 structured LogicalPlan
  -> full Olist schema + glossary prompt
  -> one Qwen3 SqlCandidate
  -> syntax-only normalization + SHA-256 fingerprint
  -> SQLGlot policy
  -> read-only bounded SQLite executor
  -> typed DirectRunResult
```

Router recognizes `QUERY`, `CLARIFY`, `UNSUPPORTED`, and `WRITE_REQUEST`; the fixture has more than
30 Vietnamese/English utterances and recognizes 100% explicit write cases. Returns/refunds route to
clarification because Olist has no such facts. Planner and generator use JSON Schema through local
Ollama, one retry at most for malformed output, `temperature=0`, context 4096, and `think=false`.

Every generated candidate records model tag, prompt version, catalog hash and SQL fingerprint.
Candidate budget is one; the 18 query cases used two model calls each. The returns and write-control
cases used zero model calls. All terminal paths include total latency and safe error text.

## Live Qwen3 Olist baseline

Command:

```bash
uv run python scripts/run_smoke.py
```

Environment/model: `qwen3:14b-q4_K_M`, digest prefix `bdbd181c33f2`, RTX A4500 Laptop 16 GiB,
SQLite catalog hash `35b8b70097954c0d41fc393f1af9a7d123b2435088198a5c7a883718ebd9efa8`.

- 20/20 cases have a typed terminal status; no crash.
- 18/20 match the expected status (two query candidates were correctly policy-blocked for unknown
  columns rather than executed).
- 18 query cases, 14 exact-result correct: **77.78% direct-baseline result accuracy**.
- p50 total latency: **26.44 s**.
- p95 total latency: **31.63 s**, below the 60 s run budget.
- Full run wall time: 8 minutes 2 seconds; runner RSS peak about 57 MiB excluding Ollama.
- Returns case: `CLARIFY`; destructive request: `WRITE_BLOCKED`, both before model calls.

Remaining failures are explicitly recorded in `docs/error_analysis.md`: customer result shape,
delivery population, review-summary column choice, and missing customer-state join. There was no
correction and no gold feedback, as required for a direct baseline.

## Gold separation and resilience

- `agentic_text2sql` runtime does not import `agentic_text2sql_eval`.
- Inference runner passes only question/database/catalog to runtime; a test inserts a secret marker
  in gold SQL and proves it never appears in predictions.
- Predictions are atomic-checkpointed after each case; evaluation reads gold only after inference.
- Malformed planner output returns `MODEL_ERROR`; invalid/non-query candidate returns `INVALID_SQL`;
  policy and execution failures have separate typed statuses.

## Bugs caught before release

1. SQLGlot parsed `not sql` as a non-query AST. Normalizer now requires an `exp.Query` root.
2. JSON Schema initially rendered as a Python dictionary in prompts. It now renders valid JSON.
3. Router confused imperative presentation text “Return the type…” with Olist return facts. The rule
   now matches `return rate`, `returns`, `returned`, and refund concepts without blocking ordinary
   result-format instructions.
4. Qwen3 thinking made the first canary take 95.6 s. Disabling thinking for structured calls reduced
   the same correct canary to 20.2 s and brought full-run p95 below 60 s.
5. Non-success terminal states initially omitted total latency. The service now records it on every
   return path; evaluator retains backward-compatible sum-of-layer timing for the baseline artifact.

## Gate conclusion

Final repository release gate:

- Ruff lint: pass;
- Ruff format: 158 files pass;
- mypy strict: 95 source files pass;
- pytest excluding explicit live model: 111 passed, 1 deselected;
- explicit live structured-output regression: 1 passed in 16.66 seconds;
- Olist data validation: 20/20;
- doctor: 8/8.

Gate P2 is `VERIFIED`. Retrieval/grounding, correction, API and UI remain outside this gate.
