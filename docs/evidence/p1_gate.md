# Gate P1 evidence — 2026-08-06

## Source and build

- Canonical ZIP SHA-256:
  `967e41e04fc306fe604e2a693f488995a8b41e5047418f8a5c8e4abd6deca784`.
- Nine CSV SHA-256/header/byte/count contracts: `datasets/olist/source_manifest.yaml`.
- Total source rows: 1,550,922.
- Generated SQLite: about 175 MiB, Git-ignored.
- Schema/views/indexes SHA-256:
  `c0e1e95a400340e776b94a30ebba0300a461cfdfeb9570b840d804bed84c0f54`.
- Logical database SHA-256, first and second full build:
  `f801d5b30e63064f396c1db800751b1efb64661193f88aa4fd439ee567feac5e`.
- Second full build: 5 minutes 43 seconds, peak RSS about 48 MiB.
- Validation after ext4 staging: approximately 12 seconds.

## Data validation

`uv run text2sql data validate olist` passed 20/20 checks:

- SQLite integrity and FK checks;
- all nine exact row counts;
- missing category and review duplication anomalies;
- raw item revenue equals order-level revenue: 1,359,164,370 cents;
- raw freight equals order-level freight: 225,190,954 cents;
- raw payments equal order-level paid value: 1,600,887,212 cents;
- geolocation centroid uniqueness;
- decimal-text to integer-cent consistency.

Ten read-only canonical Olist queries passed against pinned expected results in
`tests/golden/olist/p1_canonical_queries.yaml`. Semantic regressions prove that naïve item-payment
joins inflate revenue, while pre-aggregated views preserve it; repeat customers use
`customer_unique_id` and centroid rows are unique.

## Safety and failure paths

- AST policy rejects DML, DDL, ATTACH/DETACH, PRAGMA, multi-statement/comment obfuscation,
  SQLite internal tables and unsafe functions.
- SQLite opens with `mode=ro`, enables `query_only`, and uses an authorizer callback as a second
  denial layer.
- Timeout, row cap, byte cap and unchanged DB checksum are tested.
- Error output maps to a sanitized stable taxonomy.
- Bad archive hash, extra ZIP member, all-file header/hash/count verification, failed-build rollback,
  and tiny-fixture logical idempotency are tested.

## Bugs caught before release

1. Order-item loader initially allocated one instead of two derived cent columns. The staged build
   failed before publishing; a cardinality regression test was added.
2. Random SQLite writes/indexing on WSL `/mnt/d` spent most time in `p9_client_rpc`. Build and
   validation now perform random-I/O work in ext4 temporary storage, verify, copy to a sibling
   `.tmp`, and atomic-rename.
3. The specification's 551 repeated review/order rows was initially interpreted as number of
   affected orders. Evidence shows 551 excess rows across 547 orders; both definitions are now
   explicit and tested.

## Gate conclusion

Final repository gate:

- Ruff lint: pass;
- Ruff format: 150 files pass;
- mypy strict: 95 source files pass;
- pytest excluding explicit live-model test: 66 passed, 1 deselected;
- source verification: 9/9 files and 1,550,922 rows;
- Olist validation: 20/20 checks;
- doctor: 8/8 checks.

Gate P1 is `VERIFIED`. Phase 2 reasoning/generation has not been implemented.
