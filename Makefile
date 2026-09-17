.PHONY: sync lint format-check type test check doctor smoke synthetic benchmark-olist-r2 benchmark-olist-r2-tmux benchmark-olist-r2-recovery-tmux

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

benchmark-olist-r2:
	uv run python scripts/run_r2_olist_research.py --evaluation-id "$(EVALUATION_ID)"

benchmark-olist-r2-tmux:
	uv run python scripts/launch_r2_olist_tmux.py --evaluation-id "$(EVALUATION_ID)" --models-dir "/mnt/c/Users/ADMIN/.ollama/models" $(if $(filter 1,$(HARD_CAP_CONFIRMED)),--hard-cap-confirmed,)

benchmark-olist-r2-recovery-tmux:
	uv run python scripts/launch_r2_olist_tmux.py --evaluation-id "$(EVALUATION_ID)" --recovery-source-evaluation-id "$(SOURCE_EVALUATION_ID)" --models-dir "/mnt/c/Users/ADMIN/.ollama/models" $(if $(filter 1,$(HARD_CAP_CONFIRMED)),--hard-cap-confirmed,)
