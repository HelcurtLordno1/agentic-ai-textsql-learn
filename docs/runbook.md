# Runbook — current A1 construction

Runtime defaults to P6. The opt-in A1 implementation is on `research_local_sql_a1_20261003`.
[Canonical ledger](../realistic_project_creation_codex.md), [assessment/plan](research_plan/local_sql_a1_2026_10_03.md)
and [construction evidence](evidence/a1_construction_2026_10_03.md) distinguish source verification
from model/accuracy verification. No new inference was run during construction.
Historical operating instructions are preserved under [pre-baseline history](research_history/pre_baseline_2026_10_01/docs/runbook.md).

The user requested code only and will run checks later. No final-source tests or model runs were
executed after that instruction. Use the [handoff guide](a1_run_after_coding.md) for the final
commands; the sections below describe future operations, not completed verification.

Managed tmux commands, NVIDIA Administrator clock-cap commands and full Spider/Olist resume
examples are in [handoff guide §6–9](a1_run_after_coding.md). New controller variants are opt-in;
[novelty assessment](research_plan/novelty_and_repairability_2026_10_03.md) records prior art,
narrow contract coverage, latency limits and the ablations required for a research claim.
The tmux manager never deletes a resource latch or changes a frozen experiment's settings.

The dependency/type fix on 2026-10-07 passed `make check-static` (Ruff/format/mypy only).
Use [corrected commands](run_commands_2026_10_07.md); pytest and local-model runs remain pending.

## Model-free verification

```bash
make sync
make format
make check-static
# Includes pytest; run when you want the full test suite.
make check
uv run text2sql doctor
uv run text2sql data build olist
uv run text2sql data validate olist
```

`make check` excludes Ollama tests. Synthetic tests use fake providers and read-only SQLite.
Existing Olist integration tests may use the local database; this does not load a model.
Offline artifact inventory is reproduced with the command in the assessment document.
Case-level audit output belongs in ignored `data/artifacts`; raw data, generated DBs, indexes,
traces, predictions, model blobs and secrets must stay outside commits.

## Prepare a future pilot (not executed yet)

Review model/template/digest and stale jobs first. After a shutdown, require safe idle RAM/swap/GPU
and only a guarded one-case pilot before checkpoint resume. The Olist 78 W incident exception
still requires the OS/NVIDIA Administrator cap and a verified new pilot specified in AGENTS.
This branch offers only conservative profiles, not that exception.

Start Ollama with one resident model and parallelism one:

```bash
uv run python scripts/serve_ollama_guarded.py --profile acceptance-safe --sample-seconds 0.5
```

The suite/one-command wrapper sets explicit offload (one layer; CPU fallback zero), checks
resources before spawning, samples throughout the child at 0.5 seconds, stops its process group
on sensor failure or threshold breach and unloads **all** resident model names. Both embedding
and generation requests use `keep_alive=0`; no concurrent embedding/generation residency.
Do not manually set `TEXT2SQL_GUARDED_RUN`; it is the wrapper's internal marker.

Limits: available RAM ≥14 GiB; swap <0.25 GiB; VRAM <6144 MiB; GPU temperature <68 C;
power <70 W. Utilization is recorded. Each suite batch has exactly one case followed by
at least 60 seconds cooldown, including the last pilot batch. Stop/error never auto-retries.
`*.resource-stop.json` records the reason and peak and latches the run. Keep the checkpoint
and stop record; external remediation and an independently reviewed one-case pilot are required
before an operator archives the latch. Never delete a latch just to retry a resource breach.

For one CLI query (after pilot readiness), register the database and use the monitored wrapper:

```bash
uv run text2sql ingest --db data/samples/synthetic_commerce_tiny.sqlite --db-id tiny
TEXT2SQL_PIPELINE_MODE=a1 TEXT2SQL_CRITIC_MODE=off \
  uv run python scripts/run_guarded_local.py -- uv run text2sql ask \
  --db-id tiny --question 'How many orders?' --no-correction
```

For API/UI, run the API under `run_guarded_local.py` as a monitored command and run the UI
separately; bind both to localhost. UI itself does not call Ollama. Model-free API/CLI tests
use a fake runtime. Direct model commands outside a guard now fail before HTTP generation.
`run_guarded_local.py` is a single-command wrapper; suites always use their suite wrapper.

## Treatment flags and one-case suite pilot

- P6 control: `TEXT2SQL_PIPELINE_MODE=p6`, JSON format and existing pinned model. Safety settings
  differ from the historical P6 report; use a new matched control checkpoint.
- E2 construction: `a1`, critic `off`, current Qwen and `--no-correction`.
- E4 shadow: same topology/model, critic `shadow`; never changes output.
- E5 treatment: critic `repair` and `--correction`; at most one repair. Current admission supports
  explicit ranking contradictions and freezes other SQL structure. LLM-only findings remain shadow.

```bash
TEXT2SQL_PIPELINE_MODE=a1 TEXT2SQL_CRITIC_MODE=off \
  uv run python scripts/run_guarded_spider.py \
  --profile acceptance-safe --batch-size 1 --cooldown-seconds 60 --max-batches 1 \
  --manifest evals/configs/spider-laptop-200.json \
  --predictions evals/predictions/a1-qwen-off-pilot.jsonl \
  --report evals/reports/a1-qwen-off-pilot.json --no-correction

TEXT2SQL_PIPELINE_MODE=a1 TEXT2SQL_CRITIC_MODE=off \
  uv run python scripts/run_guarded_acceptance.py \
  --profile acceptance-safe --batch-size 1 --cooldown-seconds 60 --max-batches 1 \
  --predictions evals/predictions/a1-olist-off-pilot.jsonl \
  --report evals/reports/a1-olist-off-pilot.json --evaluation-id a1-olist-off-pilot
```

These are future pilot commands, not approval to run full suites now. Spider release inference
requires a known commit and a clean tracked tree by default. Construction pilots can explicitly
use `--allow-dirty-source`, which retains source-hash checkpoint pinning. Construction is
left uncommitted for review.
Do not reuse historical prediction paths. `*.runtime.json` freezes source/config/manifest;
changing topology, model, prompts or budgets refuses resume. Existing checkpoints without this
identity are not silently adopted. Database/index/profile identity is included; `*.backend.json`
pins installed model/template/backend per database. Resource summaries persist on successful
batches too, and a local workload lease covers execution/unload/cooldown across WSL workspaces.
Original reports and their evaluator behavior are preserved.

## SQL-specialist preparation

No model was downloaded or converted. After reviewing an installed specialist and its actual
Ollama template, set `TEXT2SQL_OLLAMA_MODEL`, pin `TEXT2SQL_GENERATION_MODEL_DIGEST`, use
`TEXT2SQL_PIPELINE_MODE=a1` and `TEXT2SQL_GENERATION_FORMAT=sql_text`. The adapter omits forced
JSON and `think=false`, accepts one final SQL block, rejects incomplete reasoning/multiple blocks
and applies the same AST/read-only checks. It is an adapter seam, not a certified Arctic/OmniSQL
replication. Start with critic off because SQL-specialist ability does not imply JSON critic ability.
For a 2048-token output cap, input budget must be ≤1792 so input+output+256 ≤4096.
Estimates use UTF-8 bytes/3, not a native tokenizer; template/actual truncation review remains
a prerequisite for the pilot. No silent prompt truncation; overflow is a typed grounding error.

Freeze the variant before opening fresh gold. Report first-pass/selected/oracle, paired gains
and losses, critic false positives and UNKNOWN, retries/tokens/P95, resource peaks and stops.
Exposed Spider-200/Olist-60 are diagnostics, not fresh-schema generalization evidence.
