# V4 research snapshot: reproduction and evidence

The initial commit on `v4_research_best` captures the completed A1 `obligation-cpu`
implementation before the next upgrade. Python dependencies are pinned by `uv.lock`;
runtime/evaluation/data contracts, prompts, guarded Windows/WSL harness and tests are
included. Raw datasets, model weights, indexes, predictions, traces and secrets are
excluded. A clone can rebuild these artifacts; the original local artifacts are not
silently reconstructed or claimed to be part of Git.

## Install and deterministic checks

Use Python 3.12, uv, WSL2/Linux and `tmux`. Windows NVIDIA/Ollama are required only for
the laptop model run, not the model-free checks.

```bash
git clone --branch v4_research_best https://github.com/HelcurtLordno1/agentic-ai-textsql-learn.git
cd agentic-ai-textsql-learn
make sync
make check
```

Do not copy another machine's `.env` or set internal guard bypass markers. Start with
`.env.example`; configure local paths and the installed model names. Run the CLI help
to inspect data commands without calling a model:

```bash
uv run --frozen text2sql data --help
uv run --frozen text2sql data download olist
uv run --frozen text2sql data build olist
uv run --frozen text2sql data validate olist
```

Download/build uses the pinned Olist source contract and checksums in `datasets/olist/`;
dataset licensing is separate from code. Obtain Spider data separately and place its
`dev.json`, `tables.json` and `database/` under `data/raw/spider/spider_data/`.
The tracked `evals/configs/spider-laptop-200.json` pins the selected IDs and file hashes;
the harness refuses incompatible data. Olist cases are pinned by
`evals/configs/olist-acceptance-60.jsonl`. Index ingestion uses the configured BGE-M3
embedding model and must itself use the guarded entrypoint; consult
`scripts/run_guarded_local.py --help`. Do not run embedding and generation concurrently.

## Completed measurements and identity

The [full report](../comparison_new4_to_baseline_vn.md) contains the protocol, paired
outcomes, failure cases and limits. Spider: **142/200**, Olist: **41/60**. Historical
P6: 130/200 and 57/60. The current source at measurement had SHA-256
`b9f38c2260dece07a0b9f476ac284689a0b3e2e50a35aa65b367d2c785683193`.
It hashes runtime/evaluation source, Python/PowerShell scripts, prompt templates,
`pyproject.toml`, `uv.lock`, models config and the Olist glossary using the checkpoint
identity algorithm. Documentation-only changes do not alter that identity.

Model: `qwen3:14b-q4_K_M`, digest
`bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`.
Embedding: BGE-M3, digest
`7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`.
Ollama at measurement: 0.30.10. A different backend/version/model must create fresh
checkpoints and be reported as a reproduction attempt, not an identical continuation.
Local sampling/model/backend execution need not be bitwise deterministic across hardware.

Original final reports live locally at
`evals/reports/a1-startupfix450-20261007-{spider,olist}.json`; the sequence state and
server journals are under `data/artifacts/experiments/a1-startupfix450-20261007/`.
They remain ignored. Their metrics and provenance are documented, not uploaded as traces.

## Fresh guarded run on the authorized laptop

Use Windows PowerShell **Administrator** to apply the verified 450 MHz hard cap:

```powershell
nvidia-smi -i 0 -lgc 300,450
nvidia-smi -i 0 --query-gpu=clocks.current.graphics,temperature.gpu,power.draw.instant,power.draw.average,memory.used --format=csv
```

In WSL, with the installed model directory adjusted for the local Windows account:

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks run \
  --name v4-reproduction-20261016 --variant obligation-cpu \
  --profile qwen14b-16gb-clock-capped \
  --models-dir /mnt/c/Users/ADMIN/.ollama/models
tmux attach -t v4-reproduction-20261016
```

The harness performs one guarded pilot per benchmark and proceeds sequentially through
Spider and Olist only after valid resource/clock/checkpoint evidence. Batch=1, explicit
GPU layers=41, unload and cooldown≥60s remain mandatory. There is no unguarded shortcut.
Every run pins the current source/config/data/backend. Use a fresh name for new code;
never append upgraded predictions to the V4 checkpoint.

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks status --name v4-reproduction-20261016
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks pause --name v4-reproduction-20261016
# After a clean PAUSED state:
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume --name v4-reproduction-20261016
```

After unexpected shutdown, stale jobs must be absent, idle resources safe and the cap
reapplied; use `resume --recovery-pilot` before ordinary resume. A resource/sensor stop
is latched, preserves its evidence and does not permit an automatic retry or override.
Ctrl+b then d detaches without stopping tmux. Full completion requires both reports,
all manifest IDs and clean shutdown, not merely a live pane.
