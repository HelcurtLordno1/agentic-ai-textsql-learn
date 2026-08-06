.PHONY: sync lint format-check type test check doctor smoke synthetic

sync:
	uv sync --frozen --group dev

lint:
	uv run ruff check .

format-check:
	uv run ruff format --check .

type:
	uv run python -m mypy src

test:
	uv run pytest -m "not ollama"

check: lint format-check type test

doctor:
	uv run text2sql doctor

smoke:
	uv run text2sql ollama-smoke

synthetic:
	uv run python scripts/generate_synthetic_fixture.py
