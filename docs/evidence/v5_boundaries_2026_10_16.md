# V5-G1 mechanical boundaries

`make check`: Ruff/format284files and mypy119sourcefiles pass; **285 tests passed,
1 Ollama deselected**,42.29s. No local model calls were made.

Before editing, model-free replay reproduced all8 Olist evidence failures, the Spider
CTE unknown-column rejection and metadata read-intent write block. Afterwards, all8
contexts and complete prompts fit their unchanged budgets; the same CTE is allowed
with lexical column resolution, and the same read question routes to QUERY. Testing
all251 saved SQL candidates introduces no new rejection of a SUCCEEDED candidate;
the only allowed/blocked change is the previously false-rejected CTE.

Reproduction artifacts remain ignored at
`data/artifacts/v5-upgrade-20261016/{before,g1-replay}.json`.
Generalized fixtures live in `tests/unit/test_v5_boundaries.py`: renamed PK-free views,
charged fallback columns, overflow refusal, nested/CTE/correlated aliases, negative
unknown/ambiguous ownership and external/write SQL. SQLGlot qualifies a copy only;
candidate SQL/output positions are not rewritten by name validation. Read-only
executor and SQL safety remain independent from language routing.

This gate verifies engineering behavior. It neither rescores V4 nor establishes new
inference accuracy. Semantic planning integration follows as V5-G2.
