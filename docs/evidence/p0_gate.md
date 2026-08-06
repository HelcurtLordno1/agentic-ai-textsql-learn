# Gate P0 evidence — 2026-08-06

Environment: WSL2/Linux, Python 3.12.3, RTX A4500 Laptop 16 GiB, Ollama 0.30.10.

## Reproducible commands

```bash
uv sync --frozen --group dev
uv run ruff check .
uv run ruff format --check .
uv run python -m mypy src
uv run pytest -m "not ollama"
uv run python scripts/generate_synthetic_fixture.py
uv run text2sql doctor --json
uv run text2sql ollama-smoke
```

## Observed evidence

- Lock resolution/install: pass, 82 packages, Python 3.12.3.
- Ruff lint/format: pass.
- mypy strict: pass (93 source files in the completed canonical scaffold).
- deterministic tests: 11 passed, 1 explicit live-Ollama test deselected.
- synthetic fixture logical SHA-256:
  `42342508689fd97b106b89c5ab6c87c79cf595000138dbe45358968d66a8d31c`.
- doctor: 8/8 checks pass (Python, project/data/artifact paths, GPU, Ollama, model, disk).
- configured model: `qwen3:14b-q4_K_M`; installed digest prefix `bdbd181c33f2`.
- live structured response:

```json
{
  "language": "vi",
  "sql": "SELECT 1 AS ket_qua",
  "read_only": true
}
```

## Regression discovered during acceptance

The first live smoke failed because Pydantic emitted a Python inline-regex `pattern` that Ollama's
grammar compiler rejected. The provider now strips unsupported grammar-only `pattern` keywords
before the request, while Pydantic still validates the complete model after generation. A unit
assertion verifies this adapter behavior; the same live smoke then passed.

## Gate conclusion

P0 is `VERIFIED`. CI uses only mocked provider responses and the deterministic synthetic fixture;
it does not require Olist, Kaggle, a GPU, Ollama, or a real model. Phase 1 has not been implemented.
