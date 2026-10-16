.PHONY: sync lint format format-check type test check-static check doctor smoke synthetic

# Whole-source checks import the optional API/UI modules as well as the core.
UV_RUN = uv run --frozen --extra ui --group dev

sync:
	uv sync --frozen --extra ui --group dev

lint:
	$(UV_RUN) ruff check .

format:
	$(UV_RUN) ruff format .

format-check:
	$(UV_RUN) ruff format --check .

type:
	$(UV_RUN) python -m mypy src

test:
	$(UV_RUN) python -m pytest -m "not ollama"

check-static: lint format-check type

check: lint format-check type test

doctor:
	$(UV_RUN) text2sql doctor

smoke:
	$(UV_RUN) text2sql ollama-smoke

synthetic:
	$(UV_RUN) python scripts/generate_synthetic_fixture.py
