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
latency cost. Later Spider SQL evaluation will use the pinned official test-suite evaluator; schema
recall is not presented as execution accuracy.

P4 correction ablation uses the frozen Olist smoke cases and reports trigger category, attempted and
recovered counts, stop reason, LLM calls, repair count, correct-to-wrong regression, and end-to-end
latency. Runtime validation is gold-blind. Because local model output varies across regenerated
plans/candidates, a single favorable run is gate evidence for bounded behavior, not a stability
claim; correction remains opt-in until repeated runs and the reviewed Olist-60 holdout pass.
