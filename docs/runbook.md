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

The API lazily stages each registered database into
`/tmp/agentic-text2sql-runtime` (override with `TEXT2SQL_RUNTIME_CACHE_DIR`). Cache identity includes
the canonical source path, size, and nanosecond modification time; publication is atomic and the
copy is read-only. Keep this cache on the WSL/Linux filesystem, not `/mnt/c` or `/mnt/d`, because
SQLite scans across the Windows mount are substantially slower. It contains generated databases
and must never be committed. A changed source automatically gets a new cache identity.

Query submission is asynchronous. Query Studio polls only its active result fragment and does not
hold the whole Streamlit script in a sleep loop, so users may switch workspaces while inference is
running. History intentionally fetches lightweight summaries and loads only the selected run. The
drag organizer is opt-in; leave it disabled for the fastest initial render.
The tracked Streamlit config disables source-file watching: WSL polling across this repository can
starve even the health endpoint, while production-like local use does not need hot reload. Restart
Streamlit manually after editing UI source.

Bounded correction is enabled by default for interactive API/UI requests. Disable it only when an
ablation explicitly needs first-pass behavior. A successful query shows the model's self-reported
confidence plus Layer 4 validation; the former is not accuracy. Free-form per-query accuracy is
`n/a` without an independently supplied reference answer. Failed runs still expose attempted SQL,
schema evidence, typed validation error, and correction diagnostics rather than a blank output.

For the verified 16 GiB laptop GPU, start Ollama through the fail-closed monitor. It binds locally,
limits Ollama to one request, pins 12 low-priority logical CPU cores, uses Flash Attention and a
quantized KV cache, and terminates the whole Ollama process group on a threshold breach:

```bash
uv run text2sql hardware-health --profile interactive-balanced
uv run python scripts/serve_ollama_guarded.py --profile interactive-balanced
```

The interactive profile keeps at most two models resident; Qwen receives a bounded six-layer GPU
offload while the much smaller BGE model may use a small amount of VRAM. The acceptance command
below instead unloads checkpoints, runs one case per batch, and cools for 20 seconds. It checkpoints
each case, so `--resume` continues from the exact persisted prefix after an interruption.

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

For a long acceptance, start a second terminal with the acceptance profile:

```bash
uv run python scripts/serve_ollama_guarded.py --profile acceptance-safe

uv run python scripts/run_guarded_acceptance.py --profile acceptance-safe
```

Thresholds are conservative for the verified RTX A4500 laptop and are not universal hardware
ratings. The guard also stops at 11.5 GiB VRAM, less than 10 GiB available RAM, or 1 GiB used swap.
The 105 W instantaneous stop is the reported 100 W hardware maximum plus 5% telemetry margin; it
does not raise the device power limit (80 W default, 85 W current on the evidence host).
Ollama's [official FAQ](https://docs.ollama.com/faq) documents parallel/context memory scaling and
explicit unload behavior; NVIDIA's
[`nvidia-smi` reference](https://docs.nvidia.com/deploy/nvidia-smi/index.html) defines the sampled
memory, temperature, power, and utilization telemetry.

Do not raise `TEXT2SQL_OLLAMA_NUM_GPU` above the selected profile. Controlled 12/14-layer pilots
independently spiked to 108.02/137.65 W and were stopped automatically; snapshot-only monitoring
missed those transients. A 10-layer long pilot also reached 101.93 W after its shorter pilot had
looked safe. P5.1 used 8 GPU layers, but the longer P6 pilot eventually observed 113.77 W at case
34 and stopped correctly. P6 therefore supersedes that operating profile with 6 GPU layers; the
33 earlier predictions are diagnostic only and cannot be mixed into release evidence.

Inference receives only the question, database and schema. After the model runtime closes, the
evaluator opens the reviewed Olist-60 gold SQL on a read-only database copy. Predictions and full
reports remain ignored; `docs/evidence/p5_gate.md` is the tracked summary.

## Gate P6 laptop release

Use a persistent `--models-dir` when a model cache must survive OS cleanup; `/tmp` is disposable.
The server refuses to start if preflight resources are already unsafe.

```bash
uv run python scripts/serve_ollama_guarded.py \
  --profile interactive-balanced \
  --models-dir data/artifacts/ollama-models

uv run python scripts/create_spider_laptop_manifest.py
OLLAMA_BASE_URL=http://127.0.0.1:11434 TEXT2SQL_OLLAMA_NUM_GPU=6 \
  uv run python scripts/run_benchmark.py \
  --manifest evals/configs/spider-laptop-200.json \
  --predictions evals/predictions/spider-p6-200-gpu6.jsonl \
  --report evals/reports/spider-p6-200.json \
  --correction --resume --max-new-cases 1
OLLAMA_BASE_URL=http://127.0.0.1:11434 TEXT2SQL_OLLAMA_NUM_GPU=6 \
  uv run python scripts/run_guarded_spider.py \
  --profile interactive-balanced \
  --batch-size 10 --cooldown-seconds 20 \
  --manifest evals/configs/spider-laptop-200.json \
  --predictions evals/predictions/spider-p6-200-gpu6.jsonl \
  --report evals/reports/spider-p6-200.json

OLLAMA_BASE_URL=http://127.0.0.1:11434 uv run python scripts/run_guarded_acceptance.py \
  --profile acceptance-safe \
  --predictions evals/predictions/olist-p6-60.jsonl \
  --report evals/reports/olist-p6-60.json \
  --evaluation-id olist-acceptance-60-p6-v1
```

The pilot must produce one atomic prediction and the supervisor must remain alive before removing
`--max-new-cases`. The laptop profile is 200 cases across 20 databases, so interruption/resume is
the normal operating mode. The guarded runner unloads both models every ten cases and cools for 20
seconds, bounding prompt-cache growth and accumulated load. Full Spider-1034 remains available via
`spider-release-1034.json` as optional P6.1 on stronger hardware; never present the laptop score as
full dev. Never commit predictions, detailed reports, indexes, model blobs, raw Spider data, or
databases. When complete, export only the gold-free portfolio summary:

```bash
uv run python scripts/export_demo_artifacts.py \
  --report evals/reports/spider-p6-200.json \
  --output docs/demo_assets/p6_spider_release.json

uv run python scripts/build_release_report.py \
  --olist-report evals/reports/olist-p6-60.json \
  --spider-report evals/reports/spider-p6-200.json \
  --retrieval-ablation data/artifacts/p3_1/spider_holdout_100_schema_recall.json \
  --correction-ablation evals/reports/olist-grounded-correction-p4.json \
  --output evals/reports/p6-release.json
```
