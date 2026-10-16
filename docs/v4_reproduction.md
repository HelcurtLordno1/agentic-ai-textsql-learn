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

## Rebuild the retrieval indexes on a fresh machine

`text2sql ingest` registers a database; it does **not** build the FAISS/BM25 index.
For a comparable run, prepare all21 semantic indexes before starting the benchmark.
With data and both models installed, configure `OLLAMA_BASE_URL` for the existing idle
local Ollama endpoint, one loaded model/parallel request, and apply the hardware cap
above. No generation workload may run at the same time. The following command builds
one database at a time under continuous Windows/WSL monitoring, explicit CPU embedding
offload0, unload and cooldown60s. Index publication/cache checkpoints are atomic;
any failed guarded child stops the loop. Existing stop latches are never removed.

```bash
TEXT2SQL_MONITOR_WINDOWS_HOST=true uv run --frozen --extra ui --group dev python - <<'PY'
import json
import subprocess
import sys
from pathlib import Path

root = Path.cwd()
manifest = json.loads((root / 'evals/configs/spider-laptop-200.json').read_text())
databases = [('olist', root / 'data/processed/olist.sqlite')]
databases += [(name, root / f'data/raw/spider/spider_data/database/{name}/{name}.sqlite')
              for name in sorted(manifest['database_sha256'])]
builder = '''
import sys
from pathlib import Path
from agentic_text2sql.settings import Settings
from agentic_text2sql.adapters.embeddings.ollama_embeddings import OllamaEmbeddingClient
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer2_grounding.service import IndexService
from scripts.build_indexes import MODEL, MODEL_DIGEST, semantic_aliases
s = Settings()
db_id = sys.argv[2]
client = OllamaEmbeddingClient(s.ollama_base_url, MODEL, num_gpu=0)
try:
    if client.model_digest() != MODEL_DIGEST:
        raise ValueError('Embedding model digest mismatch')
    catalog = SQLiteIntrospector().inspect(Path(sys.argv[1]), db_id)
    service = IndexService(s.resolved_data_dir / 'indexes/p3_1_semantic', MODEL,
        MODEL_DIGEST, lambda texts: client.embed(texts, batch_size=32))
    built = service.build(catalog, semantic_aliases() if db_id == 'olist' else None)
    print(built.model_dump_json(indent=2), flush=True)
finally:
    client.close()
'''
for db_id, database in databases:
    subprocess.run([sys.executable, '-m', 'scripts.run_guarded_local',
        '--profile', 'qwen14b-16gb-clock-capped', '--stop-file',
        str(root / f'data/artifacts/index-reproduction-{db_id}.resource-stop.json'),
        '--', sys.executable, '-c', builder, str(database), db_id], check=True)
PY
```

The actual Ollama endpoint/model versions must match the identities above. FAISS bytes
and model outputs can still differ across backends; compare catalog/model/document
identities and record rebuilt versions. Do not borrow cached predictions to claim a
fresh result. The V4 Git archive was tested without local data:255 tests pass,5
dataset-dependent integrations skip,1 Ollama test is deselected; no inference occurred.
