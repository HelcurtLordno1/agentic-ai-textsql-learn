# V6: fresh-clone reproduction

Updated29October2026. Branches: `v6_best_work` and `main`. Software variant:
A1 `v5-contracts`; P6 remains default. Historical results: Spider151/200 and
Olist54/60, with240CPU +20GPU predictions. A new CPU-only evaluation reproduces
the method, not the original mixed campaign's checkpoints/timing or guaranteed SQL.

The release includes runtime/evaluation code, tests, prompts, pinned dependencies,
data/schema/glossary contracts, evaluation manifests and monitored launchers.
Raw data, DBs, indexes, model weights, predictions, traces, secrets and private
mentor conversations remain local. Gold belongs only to the offline evaluator.

## 1. Install and verify without model execution

Python3.12, uv, Git and Make are required. Model-free checks work on Linux without
models/GPU. The benchmark harness requires WSL2, tmux, Windows PowerShell interop,
NVIDIA telemetry, `ip`, `wslpath` and Windows Ollama. Measured host:32GiBRAM/16GiBVRAM.

```bash
git clone --branch v6_best_work https://github.com/HelcurtLordno1/agentic-ai-textsql-learn.git
cd agentic-ai-textsql-learn
make sync
make check
cp .env.v6.example .env
```

Run checks before creating `.env`; configure the endpoint for your machine.
The template enables question-bound contracts and owner feedback, retaining V5
schema recovery/scope fixes. CLI `ask` also needs `--correction`; the benchmark
variant sets correction automatically. `make check` excludes the Ollama test;
optional dataset integrations skip if local data is absent.

The [recipe](../configs/experiments/v6_contracts_cpu300.json) is a reference;
CLI variant/profile flags select actual settings rather than loading this JSON.
CPU0/CPU8/promptbatch64, context4096, f16KV/noFA, input2800/output768,
max3generationHTTPattempts, case900s/request300s remain bounded. Proxy idle derives
330s, without increasing the HTTP budget. Old profiles/defaults remain intact.

## 2. Data contracts and installation

Run from the repository root:

```bash
uv run --frozen --extra ui --group dev text2sql data download olist
uv run --frozen --extra ui --group dev text2sql data build olist
uv run --frozen --extra ui --group dev text2sql data validate olist
uv run --frozen --extra ui --group dev python scripts/download_spider.py
```

Olist download/build verifies the pinned source manifest, CSV checksums/headers/counts,
integer-cent money representation, SQLite integrity/FKs and semantic views. Output is
`data/processed/olist.sqlite`. Spider's checksum-verified downloader extracts
`dev.json`, `tables.json` and `database/` into `data/raw/spider/spider_data/`.
If the upstream download is unavailable, obtain the licensed pinned data separately;
do not substitute an archive with different content hashes or modify the benchmark manifest.

The tracked `evals/configs/spider-laptop-200.json` pins 200 selected IDs, 20 databases
and file hashes. `evals/configs/olist-acceptance-60.jsonl` pins 60 reviewed cases.
Code licensing is MIT; dataset/model licenses and attribution are separate.
`text2sql ingest` registers a database but does not build its semantic retrieval index.

## 3. Models, Windows server and hardware settings

Install the models in Windows Ollama; downloading weights does not run a benchmark:

```powershell
ollama pull qwen3:14b-q4_K_M
ollama pull bge-m3:latest
```

Expected digests are pinned in `configs/models.yaml` and the V6 recipe:

```text
generation bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8
embedding  7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab
```

Ollama version at measurement was 0.30.10. Verify `/api/tags` against both digests before
embedding or inference. Tags alone are insufficient: a different model/backend must be
reported as a new reproduction attempt, with fresh checkpoints and measured results.

On the authorized laptop, reapply the hardware cap after a Windows reboot using
PowerShell **Administrator**:

```powershell
nvidia-smi -i 0 -lgc 300,300
nvidia-smi -i 0 --query-gpu=clocks.current.graphics,temperature.gpu,power.draw.average,power.draw.instant,memory.used,utilization.gpu --format=csv
```

The CPU profile still monitors the GPU, including clock/power. This specific laptop
authorization is not a blanket authorization to reuse the limits on another machine.
Keep the guard limits: RAM ≥ 8 GiB, swap/pagefile < 0.25 GiB, VRAM < 14 GiB,
temperature < 68°C, power < 70 W, graphics clock ≤ 300 MHz. Never raise a stop threshold
to finish a run; any sensor/resource breach stops the workload and preserves its latch.

The initial Windows Ollama endpoint must be reachable from WSL at the default route
gateway on port 11434, idle with `/api/ps` returning no models. Configure the existing
app accordingly, or close it and start a dedicated server in a Windows terminal:

```powershell
$env:OLLAMA_HOST = '0.0.0.0:11434'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_MAX_QUEUE = '2'
$env:OLLAMA_KEEP_ALIVE = '0'
ollama serve
```

Allow only the local/WSL connectivity needed by this installation. Do not run a second
server on the same port. In WSL, get the gateway with `ip route show default` and set
`.env` to `OLLAMA_BASE_URL=http://<gateway>:11434` for guarded index preparation.
Keep this server idle outside guarded work. Benchmark execution creates its own
Windows native guardian on port 11436 and WSL proxy on port 11435; both must be free.

## 4. Rebuild all 21 semantic indexes, one guarded database at a time

Stop generation workloads first. The following builder only inspects catalogs and
embeds catalog documents/domain aliases; it does not feed benchmark gold into indexing.
CPU embedding offload is explicit0, requests are sequential, publication/cache writes
are atomic, the guard monitors Windows/WSL continuously, and each child unloads/cools
for 60 seconds. Use fresh stop-file names if starting an independently authorized attempt;
never delete a latch to retry a failed workload.

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
        MODEL_DIGEST, lambda texts: client.embed(texts, batch_size=1))
    built = service.build(catalog, semantic_aliases() if db_id == 'olist' else None)
    print(built.model_dump_json(indent=2), flush=True)
finally:
    client.close()
'''
for db_id, database in databases:
    subprocess.run([sys.executable, '-m', 'scripts.run_guarded_local',
        '--profile', 'qwen14b-cpu300-stable', '--stop-file',
        str(root / f'data/artifacts/v6-index-01-{db_id}.resource-stop.json'),
        '--', sys.executable, '-c', builder, str(database), db_id], check=True)
PY
```

Verify that `data/indexes/p3_1_semantic/<db_id>/active.json` exists for Olist and each
of the 20 selected Spider databases. The runtime validates catalog/model/document and
payload identities. Rebuilt FAISS bytes or model outputs can differ across backends;
the new run pins the actual rebuilt bundles. Do not borrow predictions to claim freshness.

## 5. Freeze inputs and run independent pilots

Verify safe dual-host idle, no stale workers/resident models, cap300MHz, matching
model digests,21semantic indexes and free ports11435/11436. Record the release commit
with `git rev-parse HEAD`. Keep HEAD/source/config/.env/data/index/model identities
fixed while inference is active. Do not run generation and embedding concurrently.
The historical GPU41/batch16 workload breached power limits and must not be retried;
this fresh recipe explicitly usesCPU0. No model run was started for this release.

Use a fresh session name and real Windows model directory:

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks run \
  --name v6-cpu-repro-01 --variant v5-contracts \
  --profile qwen14b-cpu300-stable \
  --models-dir '/mnt/c/Users/<WindowsUser>/.ollama/models' --max-batches 2
tmux attach -t v6-cpu-repro-01:monitor
```

The two-batch boundary runs one Spider and one Olist pilot, then cleanly pauses.
Inspect both suite pilot states, raw native/WSL resource journals, CPU residency and
owned cleanup. Batch1, cooldown60s and continuous Windows/WSL0.5s monitoring remain
mandatory. Review saved pilot outputs offline after cleanup; never feed gold to runtime
or tune frozen prompts midway. Any sensor/resource breach stops BOTH suites, preserves
checkpoints/latches and forbids automatic retry/fallback/threshold increases.

After both pilots pass, continue the SAME BOOT's cleanly paused sequence:

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume --name v6-cpu-repro-01
```

The remaining Spider workload runs first, then remaining Olist. Predictions:
`evals/predictions/v6-cpu-repro-01-{spider,olist}.jsonl`; reports: `evals/reports/`;
plan/state/logs: `data/artifacts/experiments/v6-cpu-repro-01/`. All are ignored.

## 6. Monitor, pause and reboot boundary

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks status --name v6-cpu-repro-01
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks pause --name v6-cpu-repro-01
```

Detaching tmux is not pausing. Wait forPAUSED and null owned worker/server/proxyPIDs
before shutdown; manual pause never auto-resumes. Do not delete a resource stop latch.

Reboot limitation: the generic `resume --recovery-pilot` performs ONE pending pilot
and retains prior suite flags; it is not the historical task-local controller that
invalidated old-boot pilot flags and recovered EACH pending suite independently.
Do not treat that command alone as two-suite reboot qualification. After reboot,
reconfirm300–300MHz and safe idle/no stale models; a reviewed per-suite recovery
controller is required before continuing both pending suites. Original machine-specific
helpers/checkpoints remain local and must not be copied to an unrelated clone.
The fresh-run recipe above supports same-boot execution/manual pause; full portable
multi-suite reboot automation is not claimed by this release.

## 7. Offline evaluation and result interpretation

Harness completion requires reports and owned cleanup validation. Scoring is in
`src/agentic_text2sql_eval/`. Preserve failures and origin for every case; runtime
must not import evaluator/gold. Optional saved-output audit scripts require their
original local bundles and are not fresh-clone prerequisites.

- Spider: `spider-release-v2-outer-order`, read-only execution, timeout10s/rowcap100000;
  outer ORDER BY controls row order, unordered multiset otherwise, column permutations
  up to width8. Local200/20DB, not official hidden test or full1034dev. Historical
  result151/200; V5=143/200, paired8gains/0loss.
- Olist: `olist-preview-v2`, compare saved preview, preserve column position and each
  case's ordering/tolerance. Historical54/60; V5=50/60, paired4gains/0loss;
  P6=57/60. Do not replace preview scoring with full-result accuracy under the same name.

Both datasets have been inspected in development. Fresh acceptance is required for
new generalization claims. No raw historical prediction bundle is published, so this
release supports a NEW evaluation, not verification of every old row. A fixed seed
cannot ensure identical outputs on different backends/hardware. Historical GPU power
stop and CPU transport failure remain preserved; they were not relabeled COMPLETE.

Historical mixed serviceP50/P95: Spider71.46/97.77s, Olist113.52/146.50s. Successful
batches totaled12h04m52s, including4h20mcooldown. These are descriptive, not an ETA
or matched speedup. Estimate a freshCPU run from its own guarded pilots.

Code isMIT; models/dependencies/datasets retain their own licenses and Olist attribution.
