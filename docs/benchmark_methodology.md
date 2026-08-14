# Benchmark methodology

Inference receives question/database/config only. Gold-aware evaluation begins after predictions
are checkpointed and inference has stopped. Runtime cannot import `agentic_text2sql_eval`.

Olist is the application benchmark. It measures result equivalence and explicit semantic traps;
physical-only and semantic-view retrieval are separate ablations. Spider measures cross-domain
generalization and never defines Olist business behavior.

Spider P3.1 uses two pinned manifests validated against the dev file SHA-256:

- mini-100: deterministic domain/AST-complexity regression set, 100 unique rows, 20 domains;
- holdout-100: 100 disjoint rows, evaluated once after P3.1 retrieval code froze, 19 domains.

Schema metrics qualify case-insensitive SQLite identifiers to `table.column` through SQLGlot
scopes. Reports include macro/micro table and column recall at k=5/10/20, context precision,
declared-FK recall conditional on FK cases, general join-edge recall, final rendered tokens and
component latency. Cases without gold columns/FKs are excluded from those macro denominators.

Latency reports query embedding separately from warm BM25/FAISS/fusion/linking. End-to-end Olist
latency includes planning, embedding, grounding, generation, policy and execution. Model digest,
prompt version, hardware context and dataset/manifest hashes accompany gate evidence.

Retrieval is not considered useful from recall alone. A same-version full-schema versus grounded
generation ablation must show no result-accuracy regression and report both prompt-token savings and
latency cost. P6 reports local read-only Spider-dev execution equivalence with its exact comparator
contract; schema recall is not presented as execution accuracy or as a hidden-test leaderboard.

P4 correction ablation uses the frozen Olist smoke cases and reports trigger category, attempted and
recovered counts, stop reason, LLM calls, repair count, correct-to-wrong regression, and end-to-end
latency. Runtime validation is gold-blind. Because local model output varies across regenerated
plans/candidates, a single favorable run is gate evidence for bounded behavior, not a stability
claim; correction remains opt-in until repeated runs and the reviewed Olist-60 holdout pass.

P6 laptop release uses 200 pinned cases: domain-balanced regression-100 and a disjoint holdout-100.
Together they cover all 20 databases and expose partition, complexity and database slices. It hashes
`dev.json`, `tables.json`, each SQLite database and every selected row. Rows are reordered only by
database/partition/original index so runtime can reuse one catalog while atomic checkpoints remain a
strict manifest prefix. Full Spider-1034 uses the same evaluator as optional P6.1 and must never be
inferred from or conflated with the laptop score.

The local execution evaluator is intentionally described as local Spider-dev equivalence, not the
official hidden Spider leaderboard. It treats gold `ORDER BY` as ordered, otherwise compares row
multisets, permits candidate column permutations up to eight columns, normalizes finite numeric
values to six decimals, and fails closed on evaluation timeout or SQLite error.
Result materialization is capped at 100,000 rows per query to prevent an incorrect cross join from
exhausting laptop memory; exceeding the cap is an evaluator execution failure, never a pass.
Before live inference, an exact-gold evaluator self-test must score all 1,034 dev rows correctly.
SQLite legacy text with malformed UTF-8 is decoded deterministically with replacement characters in
both runtime and evaluator, avoiding environment-dependent execution failures while preserving
candidate/gold comparability.
