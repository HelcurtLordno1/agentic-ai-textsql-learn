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

OLLAMA_BASE_URL=http://127.0.0.1:11434 uv run python scripts/run_guarded_acceptance.py \
  --profile acceptance-safe \
  --predictions evals/predictions/olist-p6-60.jsonl \
  --report evals/reports/olist-p6-60.json \
  --evaluation-id olist-acceptance-60-p6-v1
```

The legacy P6 Spider report is 130/200 on the pinned stratified 200-case manifest. Do not rerun its
old six-layer/batch-ten commands on this laptop. R2 uses the same manifest for matched accuracy,
but the safer one-layer profile means latency is **not** an apples-to-apples comparison. Spider has
no Olist-certified semantic proof catalog, so this run explicitly uses `planning_mode=hybrid` and
`candidate_mode=legacy`; do not describe it as an Olist champion--challenger generalization result.

For a fresh Spider run, verify the Administrator `nvidia-smi -i 0 -lgc 300,900` hard clock cap is
active, no stale model job remains, and idle resource readings are safe. The launcher refuses an
occupied Ollama port, unsafe preflight, or a resource-stop lock. It starts a guarded server and a
one-case guarded pilot, then automatically continues from the same checkpoint only if the pilot
passes. Both guards sample every 0.5 seconds. Each case is atomically checkpointed, models unload
between cases, and a 60-second cooldown follows each non-final case. Do not alter code, index,
manifest, model, runtime settings or committed revision during a run or resume.

```bash
cd "/mnt/d/desktop_informations/vnpt ai/agentic_text_to_sql"
uv run python scripts/launch_r2_spider_tmux.py \
  --evaluation-id spider-r2-hybrid-200-v1 \
  --session spider-r2-hybrid-200-v1 \
  --models-dir /mnt/c/Users/ADMIN/.ollama/models \
  --hard-cap-confirmed
tmux attach -t spider-r2-hybrid-200-v1
# Detach without stopping: Ctrl-b, then d
watch -n 2 'jq "{state,phase,checkpoint,total_cases,observed_peak,reason}" evals/reports/spider-r2-hybrid-200-v1.progress.json; tail -n 10 evals/reports/spider-r2-hybrid-200-v1.benchmark.log'
```

For an intentional interruption, press Ctrl-C in the benchmark window and wait for its `SPIDER_PAUSED`
status and server cleanup. After safe idle checks, resume with the **same** evaluation ID and a new
tmux session name; the launcher repeats the one-case pilot, then continues the remaining manifest:

```bash
uv run python scripts/launch_r2_spider_tmux.py \
  --evaluation-id spider-r2-hybrid-200-v1 \
  --session spider-r2-hybrid-200-v1-resume1 \
  --models-dir /mnt/c/Users/ADMIN/.ollama/models \
  --hard-cap-confirmed
tmux attach -t spider-r2-hybrid-200-v1-resume1
```

If `*.resource-stop.json` appears, do **not** delete it or retry automatically. Review its measured
reason/peak, check hardware and seek operator direction before a fresh one-case pilot. The initial
Spider R2 run stopped at 34/200 when the operator raised the OS clock minimum to 900 MHz while the
old guard still enforced 600 MHz. Its incident file is retained. After reviewing its clock-only
stop (peak 2,347 MiB VRAM, 56 C, 53.42 W, zero swap), the user approved a 900--1200 MHz hard cap.
Only the guard clock ceiling changed; the inference source, model settings, index and manifest did
not. A one-time provenance migration audits the exact Git diff, validates the 34-case prefix, and
records both source revisions and the transition index. Run this **once after the new guard commit
is pushed and the old jobs are absent**, then resume with a new tmux session and explicit reviewed
clock-stop acknowledgement:

```bash
uv run python scripts/migrate_spider_clock_guard.py \
  --evaluation-id spider-r2-hybrid-200-v1
uv run python scripts/launch_r2_spider_tmux.py \
  --evaluation-id spider-r2-hybrid-200-v1 \
  --session spider-r2-hybrid-200-v1-resume1200-1 \
  --models-dir /mnt/c/Users/ADMIN/.ollama/models \
  --hard-cap-confirmed --acknowledge-clock-stop
tmux attach -t spider-r2-hybrid-200-v1-resume1200-1
```

If the new session is interrupted without a threshold breach, use a fresh session name with the
same evaluation ID and `--acknowledge-clock-stop`; do not run the migration again. A new session
resource-stop file blocks further restarts pending a separate incident review. A failed
provenance check likewise requires investigation; never merge or overwrite incompatible checkpoints.
At 170/200, the continuation stopped because the one-case child hit the *wrapper's* 360-second
deadline during an in-flight Ollama HTTP request. This is a bounded wall-time stop, not evidence
of a GPU/thermal/memory breach or a completed Spider score. Its separate incident record reports
58 C, 66.34 W, 1,790 MiB VRAM, zero swap, and 22.39 GiB available RAM. The inference code and
saved 170 predictions are unchanged. After reviewing that record and confirming idle safety,
commit the deadline-only launcher/migration revision, run the one-time audited migration, and
repeat a guarded one-case pilot with a 900-second *per-case* maximum. Continuous 0.5-second
resource monitoring, batch size 1, model unload, 60-second cooldown, and all hardware breakers
remain unchanged. Do not automatically retry if this larger deadline or a resource breaker trips.

```bash
uv run python scripts/migrate_spider_deadline_guard.py \
  --evaluation-id spider-r2-hybrid-200-v1 \
  --stop-session spider-r2-hybrid-200-v1-resume1200-2
uv run python scripts/launch_r2_spider_tmux.py \
  --evaluation-id spider-r2-hybrid-200-v1 \
  --session spider-r2-hybrid-200-v1-resume900-1 \
  --models-dir /mnt/c/Users/ADMIN/.ollama/models \
  --hard-cap-confirmed --acknowledge-clock-stop --acknowledge-deadline-stop \
  --batch-timeout-seconds 900
tmux attach -t spider-r2-hybrid-200-v1-resume900-1
```

At 174/200, that continuation hit a real GPU power threshold: 87.82 W at 1200 MHz. Never skip
the case or auto-retry this breach. The NVIDIA mobile driver rejected `-pl 75` as unsupported, so
the previous 75 W power-cap path is unavailable. For this explicitly authorized recovery, set a
lower Administrator hard **graphics-clock range 300--900 MHz**, and restore the conservative
Spider **70 W software stop**. This clock cap is not a power cap: it reduces the reachable clock
but cannot guarantee a wattage. The launcher checks the instantaneous clock and requires explicit
confirmation of the Administrator setting; the one-case guarded pilot must demonstrate safe
behavior under load before continuation. Both server and benchmark guards continue sampling every
0.5 seconds, and any new threshold breach stops the run without auto-retry. The 900-second batch
timeout is a maximum, not a fixed wait.

Run in Administrator PowerShell, one command per line:

```powershell
nvidia-smi -i 0 -lgc 300,900
nvidia-smi -i 0 -q -d POWER,CLOCK
nvidia-smi -i 0 --query-gpu=clocks.current.graphics,memory.used,temperature.gpu,power.draw,utilization.gpu --format=csv,noheader,nounits
```

Only after the `-lgc 300,900` command succeeds, stale jobs are absent, and idle resources are
safe, run in WSL. The instantaneous `900 MHz` reading alone does **not** prove the maximum lock;
the explicit Administrator command success is required.

```bash
cd "/mnt/d/desktop_informations/vnpt ai/agentic_text_to_sql"
uv run python scripts/migrate_spider_power_guard.py \
  --evaluation-id spider-r2-hybrid-200-v1 \
  --stop-session spider-r2-hybrid-200-v1-resume900-1 \
  --hard-clock-cap-confirmed
uv run python scripts/launch_r2_spider_tmux.py \
  --evaluation-id spider-r2-hybrid-200-v1 \
  --session spider-r2-hybrid-200-v1-resume900clock-1 \
  --models-dir /mnt/c/Users/ADMIN/.ollama/models \
  --hard-cap-confirmed --acknowledge-clock-stop --acknowledge-deadline-stop \
  --acknowledge-power-stop --batch-timeout-seconds 900
tmux attach -t spider-r2-hybrid-200-v1-resume900clock-1
watch -n 2 'jq "{state,phase,checkpoint,total_cases,observed_peak,reason}" evals/reports/spider-r2-hybrid-200-v1.progress.json; tail -n 10 evals/reports/spider-r2-hybrid-200-v1.benchmark.log'
```

The one-time migration records the unchanged 174-case prediction SHA, both Git revisions, the
declared Administrator clock cap, observed current clock, and transition index. Do not infer an
active hard cap from the idle clock alone. A fresh power/thermal/RAM/swap/VRAM/clock breach ends
the run and must not be automatically retried. A tmux session exists only while the tmux server
is alive; checkpoints and logs survive independently.

Full Spider-1034 remains optional P6.1 on stronger hardware and has no matched full baseline here;
never present the 200-case score as full dev. Never commit predictions, detailed reports, indexes,
model blobs, raw Spider data, or databases. When complete, export only the gold-free summary:

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
