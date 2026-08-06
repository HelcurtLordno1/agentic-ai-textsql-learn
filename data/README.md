# Data storage contract

- `raw/`, `interim/`, `processed/`, `indexes/`, and `artifacts/` contain generated or downloaded
  material and are Git-ignored.
- `samples/` contains the small deterministic synthetic fixture used by tests and CI.
- Dataset licenses do not become MIT merely because project code is MIT licensed.
- Override generated storage with `TEXT2SQL_DATA_DIR` and `TEXT2SQL_ARTIFACT_DIR` when `/mnt/*`
  I/O is too slow. Application code resolves paths through settings.

