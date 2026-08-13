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
uv sync --frozen --extra ui --group dev
uv run text2sql ingest --db data/processed/olist.sqlite --db-id olist
uv run text2sql serve --host 127.0.0.1 --port 8000
```

In a second terminal, start the local UI:

```bash
uv run streamlit run apps/streamlit_app.py
```

Open `http://127.0.0.1:8501`. The UI intentionally talks only to
`http://127.0.0.1:8000`; override it with `TEXT2SQL_API_URL` when using a different local port.
Do not expose either service publicly without adding authentication and deployment hardening.

For a 16 GiB GPU or a laptop sensitive to memory pressure, run Ollama sequentially and avoid
starting API/Streamlit during the 60-case benchmark:

```bash
OLLAMA_HOST=127.0.0.1:11434 \
OLLAMA_NUM_PARALLEL=1 \
OLLAMA_MAX_LOADED_MODELS=1 \
OLLAMA_KEEP_ALIVE=30s \
OLLAMA_CONTEXT_LENGTH=4096 \
ollama serve
```

This trades model-switch latency for bounded VRAM/RAM. The acceptance command checkpoints each
case, so `--resume` continues from the exact persisted prefix after an interruption.

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

Gate P5 acceptance is resumable and writes a checkpoint after every case:

```bash
uv run python scripts/run_olist_acceptance.py --correction --resume
```

On the verified laptop profile, use the fail-closed wrapper after starting sequential Ollama:

```bash
taskset -c 0-11 nice -n 10 env \
  OLLAMA_HOST=127.0.0.1:11434 \
  OLLAMA_NUM_PARALLEL=1 \
  OLLAMA_MAX_LOADED_MODELS=1 \
  OLLAMA_MAX_QUEUE=2 \
  OLLAMA_KEEP_ALIVE=0 \
  OLLAMA_CONTEXT_LENGTH=4096 \
  ollama serve

OLLAMA_BASE_URL=http://127.0.0.1:11434 \
uv run python scripts/run_guarded_acceptance.py \
  --batch-size 1 --cooldown-seconds 20 --ollama-num-gpu 12 \
  --maximum-gpu-temperature-c 76 --maximum-gpu-power-w 95
```

Thresholds are conservative for the verified RTX A4500 laptop and are not universal hardware
ratings. The guard also stops at 11.5 GiB VRAM, less than 10 GiB available RAM, or 1 GiB used swap.
Ollama's [official FAQ](https://docs.ollama.com/faq) documents parallel/context memory scaling and
explicit unload behavior; NVIDIA's
[`nvidia-smi` reference](https://docs.nvidia.com/deploy/nvidia-smi/index.html) defines the sampled
memory, temperature, power, and utilization telemetry.

Inference receives only the question, database and schema. After the model runtime closes, the
evaluator opens the reviewed Olist-60 gold SQL on a read-only database copy. Predictions and full
reports remain ignored; `docs/evidence/p5_gate.md` is the tracked summary.
