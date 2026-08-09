# Runbook

Run Phase 0 checks and build the Phase 1 data foundation:

```bash
uv sync --frozen --group dev
make check
uv run text2sql doctor
uv run text2sql data download olist
uv run text2sql data build olist
uv run text2sql data validate olist
uv run python scripts/run_smoke.py
uv run python scripts/download_spider.py
uv run python scripts/create_spider_mini_manifest.py
OLLAMA_BASE_URL=http://<local-host>:11434 uv run python scripts/build_indexes.py
OLLAMA_BASE_URL=http://<local-host>:11434 uv run python scripts/run_smoke.py --mode grounded
```

Only download requires Internet. The public Kaggle endpoint works without embedding credentials;
manual placement of the pinned ZIP at `data/raw/olist/olist_brazilian_ecommerce.zip` is also valid.
Build and validation stage random-I/O work in Linux temporary storage before atomic publication to
handle WSL `/mnt/*` performance. Generated data remains Git-ignored.

The smoke command stages Olist to Linux temporary storage, writes predictions incrementally under
`evals/predictions/`, closes inference, and then writes a gold-aware report under `evals/reports/`.
Both generated directories are ignored; tracked gate evidence summarizes the exact run.

P3.1 pins BGE-M3 by Ollama digest. `build_indexes.py` fails closed if the installed tag points to a
different digest. It builds immutable versioned bundles, validates the active pointer and emits
qualified mini/holdout reports under ignored `data/artifacts/p3_1/`. `run_smoke.py --mode full` and
`--mode grounded` write separate predictions/reports for a same-prompt ablation.
