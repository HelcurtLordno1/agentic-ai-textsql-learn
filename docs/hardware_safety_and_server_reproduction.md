# Hardware safety, guarded benchmarks, and fresh-server reproduction

Last updated: 2026-09-03 (Asia/Bangkok)
Operational status: laptop model runs are blocked until a hard GPU clock/power cap passes a new
one-case pilot. Non-LLM tests, documentation, and dataset verification remain safe to run.

This is the operational source of truth for protecting the development laptop and reproducing the
project on another NVIDIA Linux/WSL host. Historical benchmark results remain in
[`benchmark_full.md`](../benchmark_full.md); detailed R1 evidence remains in
[`docs/evidence/r1_resource_guard_incident.md`](evidence/r1_resource_guard_incident.md) and
[`docs/evidence/r1_olist_benchmark.md`](evidence/r1_olist_benchmark.md).

## 1. What happened and what is locked

The original P6 Olist baseline is **57/60 (95.00%)**. All three historical development/regression
failures were later rerun separately with Qwen3-14B and passed 3/3. The last case, `olist_acc_023`,
passed 1/1 at a peak of 63 C, 77.01 W, 1,922 MiB VRAM, about 0.94 GiB additional RAM, and zero
swap. The GPU cooled to 54 C afterward.

A new, locked Olist-60 v1 then progressed as follows:

- cases 1–4 reached durable `SUCCEEDED` checkpoints;
- case 5 used the full analyst path and the circuit breaker stopped the run at **78.68 W**;
- peak temperature was 64 C, VRAM 1,922 MiB, available RAM at least 22.25 GiB, and swap zero;
- Ollama and the benchmark process group were stopped and no automatic retry occurred;
- the 5-case prefix evaluated to 4/5, but it is diagnostic only, not a 60-case accuracy claim;
- the entity-owner grounding fix changed the source snapshot afterward, so v1 must not be resumed
  or mixed with a new run.

The improvement criterion for a clean v2 remains at least **58/60**, compared with the frozen
57/60 baseline. The evaluator result must be reported unchanged even if it is lower.

The incident establishes three boundaries:

1. A software watchdog can stop a process, but it cannot make repeated operation at the GPU power
   limit safe.
2. The laptop must not resume Qwen3-14B Olist work until an Administrator/OS-level clock or power
   cap is active and a new one-case guarded pilot stays below every limit.
3. A fresh source snapshot requires a fresh prediction file and evaluation ID. Never combine
   checkpoints from different commits, prompts, model digests, manifests, or hardware profiles.

## 2. Non-negotiable monitor contract

Every local-model run uses two independent layers:

```text
OS/NVIDIA hard cap
  -> guarded Ollama supervisor (continuous sampling)
     -> guarded benchmark wrapper (continuous sampling + checkpoint)
        -> one inference case
           -> atomic prediction checkpoint
              -> unload model -> cooldown -> next case
```

Both guards fail closed. A missing/broken `nvidia-smi`, malformed sensor result, timeout, unsafe
preflight, or threshold breach means stop. Do not retry automatically.

For the development laptop, the default long-run ceilings are:

| Resource | Start/run condition |
|---|---:|
| Available RAM | at least 14 GiB |
| Swap used | below 0.25 GiB |
| VRAM used | below 6 GiB |
| GPU temperature | below 68 C |
| GPU power | below 70 W |

The only calibrated exception is `olist-paper1-ultrasafe` for Qwen3-14B Olist: one GPU layer, one
case per batch, 0.5-second sampling, one model resident, unload after every case, 60-second cooldown,
VRAM below 4 GiB, temperature below 65 C, and a 78 W stop. It is not valid for Spider, another
model, another GPU, or another workload.

Historical P5/P6 revisions used `interactive-balanced`, `acceptance-safe`, and
`research-benchmark-safe` with 100–105 W stops. Those values remain documented as provenance but are
**not approved for new runs on this laptop**. The current profile definitions are tightened to the
default limits above, one resident model, and one-case benchmark batches; reproduce old results only
from their pinned historical commit, never by loosening the current checkout.

During a run, the guard samples all mandatory signals—not just before and after:

```bash
nvidia-smi \
  --query-gpu=temperature.gpu,power.draw,memory.used,utilization.gpu \
  --format=csv,noheader,nounits
free -h
```

Use the typed project view for a reproducible preflight:

```bash
uv run text2sql hardware-plan --profile olist-paper1-ultrasafe
uv run text2sql hardware-health --profile olist-paper1-ultrasafe
```

Exit code `75` means an intentional resource-guard stop. Preserve the checkpoint and incident log;
do not turn it into a failed model prediction and do not increase the threshold.

## 3. Laptop recovery and hard-cap procedure

After an unexpected shutdown:

1. Reboot and confirm no stale benchmark, Python, or Ollama runner remains.
2. Leave the machine idle until RAM, swap, VRAM, temperature, and power pass preflight.
3. Apply an OS/NVIDIA hard cap with Administrator privileges.
4. Verify the cap from both Windows and WSL/Linux.
5. Run exactly one guarded case. Only a clean pilot permits continuation.

Read-only stale-process checks:

```bash
pgrep -af 'ollama|run_.*benchmark|run_guarded|run_olist_acceptance' || true
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
uv run text2sql hardware-health --profile olist-paper1-ultrasafe
```

On the verified Windows/WSL laptop, open **PowerShell as Administrator** and apply the proposed
graphics-clock lock:

```powershell
$NvidiaSmi = "$env:WINDIR\System32\nvidia-smi.exe"
& $NvidiaSmi -q -d POWER,CLOCK,TEMPERATURE
& $NvidiaSmi -lgc 300,600
& $NvidiaSmi --query-gpu=name,clocks.gr,clocks.max.gr,power.draw,power.limit,temperature.gpu,memory.used --format=csv
```

The command must report success. A printed setting is not enough: the one-case pilot must prove
that observed power remains below 78 W while all other limits pass. Reapply and reverify the lock
after a reboot or driver reset. If the GPU/driver rejects `-lgc`, stop; do not replace it by raising
the software breaker.

Reset the graphics clock only after all model work has stopped:

```powershell
& "$env:WINDIR\System32\nvidia-smi.exe" -rgc
```

## 4. Clean Olist-60 v2 command sequence

Do not run the unguarded `scripts/run_olist_acceptance.py` directly. Use two terminals and unique v2
artifacts. Before starting, `git status --short` and the recorded provenance must identify the exact
source snapshot; the v2 paths below must not already contain results from another snapshot.

Terminal 1—guarded Ollama:

```bash
uv run python scripts/serve_ollama_guarded.py \
  --profile olist-paper1-ultrasafe \
  --sample-seconds 0.5
```

Terminal 2—one-case pilot:

```bash
test ! -e evals/predictions/olist-paper1-r1-60-v2.jsonl
test ! -e evals/reports/olist-paper1-r1-60-v2.json

OLLAMA_BASE_URL=http://127.0.0.1:11434 \
uv run python scripts/run_guarded_acceptance.py \
  --profile olist-paper1-ultrasafe \
  --sample-seconds 0.5 \
  --max-batches 1 \
  --predictions evals/predictions/olist-paper1-r1-60-v2.jsonl \
  --report evals/reports/olist-paper1-r1-60-v2.json \
  --evaluation-id olist-paper1-r1-60-v2
```

Continue only when the pilot has one durable terminal prediction, both guards stayed alive, the OS
cap was active, and the measured peak had clear margin below every stop. Continue the same locked
v2 checkpoint by removing only `--max-batches 1`:

```bash
OLLAMA_BASE_URL=http://127.0.0.1:11434 \
uv run python scripts/run_guarded_acceptance.py \
  --profile olist-paper1-ultrasafe \
  --sample-seconds 0.5 \
  --predictions evals/predictions/olist-paper1-r1-60-v2.jsonl \
  --report evals/reports/olist-paper1-r1-60-v2.json \
  --evaluation-id olist-paper1-r1-60-v2
```

If either guard reaches 78 W, do not resume this workload on the laptop. Move it to a separately
calibrated server or reduce the workload/model under a new experiment ID.

## 5. Fresh server: reproducible installation

The repository contains source, locked dependencies, dataset manifests/checksums, benchmark
manifests, tests, and sanitized evidence. It intentionally does not contain raw datasets, generated
SQLite databases, indexes, model blobs, predictions, traces, or secrets. A server reconstructs
those local artifacts as follows.

### 5.1 Host prerequisites

- Linux or WSL2, Git, `curl`, SQLite, and Python 3.12;
- `uv` and Ollama installed for the current user;
- an NVIDIA driver exposing `nvidia-smi` to the same environment as the guard;
- enough local Linux-disk space for model blobs, Olist/Spider sources, SQLite databases, indexes,
  predictions, and reports;
- outbound network only for the initial clone/model/dataset downloads.

Use a native Linux filesystem for generated data and indexes. Avoid NFS/SMB and `/mnt/c` or
`/mnt/d` for benchmark random I/O.

### 5.2 Clone, lock dependencies, and verify code

```bash
git clone https://github.com/HelcurtLordno1/agentic-ai-textsql-learn.git
cd agentic-ai-textsql-learn
git rev-parse HEAD

uv sync --frozen --extra ui --extra eval --group dev
make check
```

Record `git rev-parse HEAD` in every experiment. `make check` is non-Ollama and must pass before a
benchmark is considered reproducible.

### 5.3 Put the clone and generated artifacts on fast local storage

Clone the repository itself on a native Linux volume and keep the default repo-relative `data/`
layout for benchmark reproduction. The current Olist CLI honors `TEXT2SQL_DATA_DIR`, but the Spider
manifest/index scripts intentionally use the canonical repo-relative `data/` paths. Mixing those
layouts produces an incomplete benchmark environment.

For application runtime copies only, a separate native cache is supported:

```bash
mkdir -p "$PWD/.runtime-cache"
export TEXT2SQL_RUNTIME_CACHE_DIR="$PWD/.runtime-cache"
```

`data/`, `.runtime-cache/`, and generated evaluation outputs are local runtime state and must not be
committed. If the server uses persistent volumes, mount the entire clone on that local volume or
provide the canonical repo-relative directories consistently; do not move only half of the data
pipeline.

### 5.4 Pull and verify models

```bash
ollama pull qwen3:14b-q4_K_M
ollama pull bge-m3:latest
ollama list
uv run text2sql doctor
```

The pinned digests are in `configs/models.yaml`. If an upstream tag changes, do not edit the digest
to bypass the check; obtain the pinned artifact or open a model-upgrade experiment and rerun all
affected evidence.

### 5.5 Download and rebuild datasets

Olist is the 9-table application dataset. Spider dev is the cross-domain benchmark. Their raw files
have separate licenses and are downloaded locally, never redistributed through Git.

```bash
uv run text2sql data download olist
uv run text2sql data build olist
uv run text2sql data validate olist

uv run python scripts/download_spider.py
uv run python scripts/create_spider_mini_manifest.py
uv run python scripts/create_spider_laptop_manifest.py
```

The Olist downloader verifies the pinned archive plus all nine CSV hashes, headers, sizes, and row
counts from `datasets/olist/source_manifest.yaml`. The Spider downloader verifies the pinned archive
SHA-256 from `datasets/spider/pinned_revision.yaml`. A manual Olist fallback may place the exact
pinned ZIP at `data/raw/olist/olist_brazilian_ecommerce.zip` when using the default data path.

Build indexes only while Ollama is supervised. Generation and embedding models must not run
concurrently on the development laptop; on a server, concurrency still requires a separately
calibrated profile and explicit resource budget.

```bash
OLLAMA_BASE_URL=http://127.0.0.1:11434 uv run python scripts/build_indexes.py
uv run text2sql ingest --db data/processed/olist.sqlite --db-id olist
```

For the full benchmark path, keep the default `data/processed/olist.sqlite`. A custom
`TEXT2SQL_DATA_DIR` is suitable for Olist-only application use, but not for the current combined
Olist/Spider index script without a corresponding tested code change.

## 6. Calibrating an unfamiliar NVIDIA server

Do not assume a workstation/server is safe merely because it has more VRAM. Power, thermals,
cooling, multi-user contention, and driver telemetry differ.

1. Reserve one GPU and prevent unrelated jobs from sharing it.
2. Record GPU name, driver, power limit, clocks, VRAM, CPU/RAM/swap, Ollama version, and model
   digests.
3. Start with one GPU layer, one case, one resident model, 0.5-second sampling, unload, and cooldown.
4. Use limits below the host manufacturer's continuous ratings and below site cooling/power policy.
5. Run one guarded pilot. Increase throughput only through a reviewed profile change and another
   pilot.
6. Preserve profile values and peak telemetry in the experiment provenance.

Preflight inventory:

```bash
nvidia-smi -L
nvidia-smi -q -d POWER,CLOCK,TEMPERATURE,MEMORY
free -h
df -h . data
ollama --version
uv run text2sql doctor --json
```

The current monitor expects the guarded workload to see one NVIDIA GPU. On a multi-GPU server,
isolate one GPU at the scheduler/container level and verify that `nvidia-smi` inside the workload
reports only that device before starting. Do not run a multi-GPU benchmark until the monitor has
been extended and tested for explicit per-device selection.

## 7. Full Spider benchmark on a server

Full Spider dev contains 1,034 cases and is optional P6.1. It must use the tracked
`evals/configs/spider-release-1034.json`; never extrapolate the Spider-200 score.

First create a new server-specific hardware profile in `src/agentic_text2sql/hardware.py` with
measured limits approved for that host, add deterministic profile tests, and run `make check`.
Do **not** reuse `olist-paper1-ultrasafe` or silently loosen a laptop profile. Then use the same
server profile for both independent guards.

Pilot exactly one batch/case:

```bash
uv run python scripts/serve_ollama_guarded.py \
  --profile <approved-server-profile> --sample-seconds 0.5
```

In a second terminal:

```bash
OLLAMA_BASE_URL=http://127.0.0.1:11434 \
uv run python scripts/run_guarded_spider.py \
  --profile <approved-server-profile> \
  --batch-size 1 --max-batches 1 --cooldown-seconds 60 --sample-seconds 0.5 \
  --manifest evals/configs/spider-release-1034.json \
  --predictions evals/predictions/spider-server-1034-v1.jsonl \
  --report evals/reports/spider-server-1034-v1.json
```

If the pilot is safe, continue the exact same checkpoint, commit, manifest, model digests, seed,
prompt versions, index identity, and profile. Increase batch size only after evidence shows adequate
margin; batch size 1 is always the safest default.

```bash
OLLAMA_BASE_URL=http://127.0.0.1:11434 \
uv run python scripts/run_guarded_spider.py \
  --profile <approved-server-profile> \
  --batch-size 1 --cooldown-seconds 60 --sample-seconds 0.5 \
  --manifest evals/configs/spider-release-1034.json \
  --predictions evals/predictions/spider-server-1034-v1.jsonl \
  --report evals/reports/spider-server-1034-v1.json
```

The inference checkpoint is written before the gold-aware evaluator opens reference answers. Never
feed evaluator mismatches back into the same locked run.

## 8. Stop, resume, and reporting rules

Stop immediately when any of these occurs:

- RAM, swap, VRAM, temperature, or power reaches its profile threshold;
- either monitor fails or cannot sample continuously;
- the OS hard cap disappears;
- an unexpected competing GPU process appears;
- checkpoint progress stops or provenance no longer matches;
- the host shuts down, throttles abnormally, or reports hardware/driver errors.

After a thermal/power breach, unload models and report the observed reason and peak. Never
auto-retry. After an unexpected shutdown, require a safe idle sample and a one-case pilot before any
resume. The special laptop Olist run may not resume after another 78 W stop, even from a valid
checkpoint.

Generated files stay local and ignored:

- `data/raw`, `data/processed`, `data/indexes`, `data/artifacts`;
- `evals/predictions`, `evals/reports`, `evals/failures`;
- Ollama model blobs, runtime SQLite caches, `.env`, traces, and secrets.

Commit only source, configuration, manifests/checksums, tests, sanitized summaries, and evidence.
For a release, export a gold-free summary with the existing `export_demo_artifacts.py` and
`build_release_report.py` scripts, inspect it for sensitive paths/content, then add that sanitized
artifact deliberately.

## 9. Reproduction checklist

- [ ] Exact Git commit recorded; working tree clean for the locked run.
- [ ] `uv sync --frozen ...` and `make check` pass.
- [ ] Olist/Spider archive hashes and dataset validation pass.
- [ ] Qwen/BGE tags and digests match `configs/models.yaml`.
- [ ] Generated data lives outside Git and on a fast local filesystem.
- [ ] One GPU is isolated and continuous telemetry works.
- [ ] OS hard cap and guarded profile are recorded and verified.
- [ ] One-case pilot passes before continuing.
- [ ] Batch size, cooldown, seed, prompts, manifest, catalog/index hashes, and source commit are locked.
- [ ] Every case checkpoints atomically; guard stop never auto-retries.
- [ ] Evaluation occurs only after final inference output and reports all failures unchanged.
- [ ] `make check` passes again before any gate or release claim.
