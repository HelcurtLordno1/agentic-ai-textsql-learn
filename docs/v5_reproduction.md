# V5: clone, setup and guarded reproduction

`best_research_v5` is the published V5 source snapshot; `main` publishes the same tree.
The measured method is A1 **`v4-reliability`**, using **`qwen14b-cpu600-stable`**.
Historical experiment names retain their `v4-` prefix. P6 remains the application default;
publishing the repository on main does not promote A1 over the P6 champion.

Measured outcomes: **Spider 143/200 (71.50%)**, **Olist 50/60 (83.33%)**. See the
[full Vietnamese report](../comparison_new5_to_baseline_vn.md),
[aggregate evidence](evidence/v5_benchmark_summary.json) and
[portable recipe](../configs/experiments/v5_reliability_cpu.json).
The release includes the source, tests, prompts, locked dependencies, dataset/schema
contracts, evaluation manifests and Windows/WSL guarded harness needed to attempt a fresh run.
Datasets, SQLite databases, indexes, weights, predictions, traces, `.env` and secrets stay local.
Reproduction means rebuilding those artifacts and measuring a new run; it does not promise
identical generated SQL across hardware or silently restore the original checkpoints.

## 1. Prerequisites and model-free verification

Use Python 3.12, uv, Git and Make on Linux/WSL2. The measured model harness specifically
uses Windows Ollama/NVIDIA from WSL, PowerShell interop, `nvidia-smi`, `ip`, `wslpath` and tmux.
The original laptop has 32 GiB host RAM and 16 GiB GPU memory. Keep at least 8 GiB available
RAM during a model request; the full CPU chain reached a minimum near 8.54 GiB.

```bash
git clone --branch best_research_v5 https://github.com/HelcurtLordno1/agentic-ai-textsql-learn.git
cd agentic-ai-textsql-learn
make sync
make check
```

`make sync` uses `uv.lock`, Python 3.12, the UI extra and dev group. Checks use fake
transports/synthetic fixtures and exclude the `ollama` marker. A clone without local
datasets skips the dataset-dependent integrations; this is expected and is distinct
from a new model benchmark. Do this verification before creating a machine-specific `.env`.

The general template is `.env.example`. Optional V5 settings are in `.env.v5.example`:

```bash
cp .env.v5.example .env
```

Edit the endpoint for your installation. Never copy another machine's `.env`, internal
guard markers, experiment plan, absolute paths or checkpoints. The tmux harness records
typed settings and overrides the generation endpoint with its owned guarded backend.
The JSON recipe is an explicit reference configuration; the CLI selects it through the
variant/profile flags below rather than automatically loading that JSON file.

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

Expected digests are pinned in `configs/models.yaml` and the V5 recipe:

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
nvidia-smi -i 0 -lgc 300,600
nvidia-smi -i 0 --query-gpu=clocks.current.graphics,temperature.gpu,power.draw.average,power.draw.instant,memory.used,utilization.gpu --format=csv
```

The CPU profile still monitors the GPU, including clock/power. This specific laptop
authorization is not a blanket authorization to reuse the limits on another machine.
Keep the guard limits: RAM ≥ 8 GiB, swap/pagefile < 0.25 GiB, VRAM < 14 GiB,
temperature < 68°C, power < 70 W, graphics clock ≤ 600 MHz. Never raise a stop threshold
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
        '--profile', 'qwen14b-cpu600-stable', '--stop-file',
        str(root / f'data/artifacts/v5-index-01-{db_id}.resource-stop.json'),
        '--', sys.executable, '-c', builder, str(database), db_id], check=True)
PY
```

Verify that `data/indexes/p3_1_semantic/<db_id>/active.json` exists for Olist and each
of the 20 selected Spider databases. The runtime validates catalog/model/document and
payload identities. Rebuilt FAISS bytes or model outputs can differ across backends;
the new run pins the actual rebuilt bundles. Do not borrow predictions to claim freshness.

## 5. Two independent pilots, then at least five stable batches

Check safe idle resources, no stale Windows/WSL runners, no resident model, the hardware
cap and available ports. Keep source, Git HEAD, `.env`, data/indexes and model metadata
fixed throughout inference. Replace the model directory with the real Windows account
or configured `OLLAMA_MODELS` location. Use a fresh session name, for example:

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks run \
  --name v5-repro-01 --variant v4-reliability \
  --profile qwen14b-cpu600-stable \
  --models-dir '/mnt/c/Users/<WindowsUser>/.ollama/models' --max-batches 2
tmux attach -t v5-repro-01:monitor
```

This runs one guarded Spider case and one Olist case, then PAUSED after unload/cooldown.
Inspect both suite states, guard/native journals and model/options provenance. A live
dashboard is not enough; owned worker/server/proxy must finish cleanup before the next stage.
Use Ctrl+b then d to detach. The JSON recipe records the measured generation settings:
GPU0/CPU8/internal batch64/context4096/input2800/output768/max3 requests,
case deadline 900 s/request timeout 300 s, flash attention off, f16 KV cache.

Only while cleanly PAUSED, score the saved prefix offline without calling a model:

```bash
uv run --frozen --extra ui --group dev python - <<'PY'
import json
import sqlite3
from pathlib import Path
from agentic_text2sql.adapters.sqlite_text import decode_sqlite_text
from agentic_text2sql_eval.olist_acceptance import load_olist_acceptance, _rows_equal
from agentic_text2sql_eval.spider_release import load_release_cases, _execute, _has_order, execution_equal

root = Path.cwd()
name = 'v5-repro-01'
state = json.loads((root / f'data/artifacts/experiments/{name}/sequence-state.json').read_text())
assert state['phase'] == 'PAUSED'
assert all(state[k] is None for k in ['worker_pid', 'server_pid', 'proxy_pid'])
_, spider = load_release_cases(root / 'data/raw/spider/spider_data', root / 'evals/configs/spider-laptop-200.json')
cases = {'spider': {c.id: c for c in spider},
         'olist': {c.id: c for c in load_olist_acceptance(root / 'evals/configs/olist-acceptance-60.jsonl')}}
for suite in ['spider', 'olist']:
    rows = [json.loads(line) for line in (root / f'evals/predictions/{name}-{suite}.jsonl').read_text().splitlines()]
    for row in rows:
        c = cases[suite][row['case_id']]
        r = row['result']
        database = (root / f'data/raw/spider/spider_data/database/{c.db_id}/{c.db_id}.sqlite'
                    if suite == 'spider' else root / 'data/processed/olist.sqlite')
        with sqlite3.connect(f'file:{database.resolve()}?mode=ro', uri=True) as con:
            con.text_factory = decode_sqlite_text
            con.execute('PRAGMA query_only=ON')
            gold = _execute(con, c.gold_sql, 10)
            correct = r['status'] == 'SUCCEEDED' and (
                execution_equal(_execute(con, r['candidate']['normalized_sql'], 10), gold, ordered=_has_order(c.gold_sql))
                if suite == 'spider' else
                _rows_equal(r['result_rows'], gold, order_matters=c.result_order_matters, tolerance=c.tolerance))
        print(suite, row['case_id'], 'correct=', correct)
        assert correct, 'Qualification prefix failed; review before full continuation'
PY
```

After both pilots pass resource/cleanup and offline quality checks, run 3 more batches:

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume --name v5-repro-01 --max-batches 3
tmux attach -t v5-repro-01:monitor
```

Wait for clean PAUSED, inspect resources and repeat the offline prefix scoring above.
Only after all 5qualification batches pass, start the remaining cases:

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume --name v5-repro-01
tmux attach -t v5-repro-01:monitor
```

The sequence finishes Spider200 before Olist60. Status and graceful pause:

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks status --name v5-repro-01
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks pause --name v5-repro-01
```

Actual sensor/resource failures stop both workloads and retain evidence; no automatic retry.
After reboot, reapply the cap and require safe idle/no stale owners plus a one-case
`resume --recovery-pilot`. Each unfinished suite has its own boot identity: when both
need recovery, recover Spider first, finish only its remaining batches with `--max-batches`,
then run Olist's `--recovery-pilot` before ordinary full resume. See
[plan §12.9](../accurate_real_problem_set_plan.md#129-user-authorized-full-resume-after-reboot--2026-10-17).
Do not edit state files or reuse the original completed experiment's paths.

## 6. Completion, identities and publication boundary

Success requires `COMPLETE`, full ordered manifest IDs, final reports and owned cleanup:

```text
SUCCESS FINISH ALL: Spider 200/200 + Olist 60/60
```

New reports/predictions, `.runtime.json`/`.backend.json`, plans, native samples and guard
journals live in ignored `evals/` and `data/artifacts/` paths. Compare accuracy, paired
gains/losses, language/schema slices and service/setup/batch wall separately. Keep failures
in the denominator and preserve actual stop artifacts. A fresh clone does not contain
the old raw checkpoints referenced by the historical report; tracked aggregate evidence
provides the measurement summary, and this guide provides a new-run procedure.

Measurement development HEAD was `663879ab034dce1c604784a45504a03753926282` with uncommitted
V5 source; the publication commit is a later Git identity. The measured continuation
source digest was `76a2c89a21778e0d0bed0812c9b5343bf366ec85b59e1b7020d60e76b761990a`.
Inherited 45 CPU predictions retain their audited parent source; continuation produced 215.
Code/config in `src`, `scripts`, prompts, `pyproject.toml`, `uv.lock`, models config and
the Olist glossary is included to preserve this source fingerprint. New publication
documentation/examples do not change that hash. A new Git HEAD needs fresh provenance;
never append release output to historical checkpoints pinned to the development commit.
