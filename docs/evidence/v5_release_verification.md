# V5 publication verification — 2026-10-17

Targets: `best_research_v5` and `main` in
`HelcurtLordno1/agentic-ai-textsql-learn`. The release contains the measured
`v4-reliability` implementation, CPU profile, guarded orchestration, all its new
source/tests, locked dependencies and portable setup instructions.

## Source completeness and fresh installation

An archive of the staged Git tree was extracted into a fresh temporary directory.
It had no `.env`, local databases, indexes, weights, predictions or traces.
`make sync` installed the locked Python 3.12 environment, then `make check` passed:

- Ruff: pass; formatter: 314 files; mypy: 121 source files, no issues.
- Pytest: **336 passed, 5 skipped, 1 Ollama deselected**, 10.03 seconds.
- The 5 skips are three Olist database integrations and two Spider dataset integrations.
- The existing data-equipped workspace previously passed **341 tests**, 1 deselected,
  103.71 seconds, while producing the V5 report. No new model inference was performed.

The clean archive reproduces the measured continuation source fingerprint exactly:

```text
76a2c89a21778e0d0bed0812c9b5343bf366ec85b59e1b7020d60e76b761990a
```

The fingerprint covers `src`, Python/PowerShell scripts, prompt templates,
`pyproject.toml`, `uv.lock`, models config and the Olist glossary. No modified or
untracked source/setup file under `src`, `scripts`, `tests` or `configs` was omitted.
Publication documentation and examples are separate from the measured algorithm.

## Portable setup contract

The [recipe](../../configs/experiments/v5_reliability_cpu.json) was checked against
the live typed profile/variant and the completed checkpoint's effective settings;
all settings match after excluding machine-specific endpoint/path fields.
`.env.v5.example` validates GPU 0 / CPU 8 / batch 64, deadline 900 s / request 300 s and both
reliability flags. Both inline Python procedures in the
[reproduction guide](../v5_reproduction.md) parse without executing a model.

The guide covers checksum-verified data download/build, model identities,
Windows/WSL connectivity, guarded sequential index rebuilding, independent pilots,
offline prefix quality checks, five qualification batches, full execution and recovery.
Fresh rebuilt indexes or inference on another backend can differ; new checkpoints
pin those actual identities instead of adopting old predictions.

## Artifact and history boundary

Only aggregate benchmark evidence is published in
[v5_benchmark_summary.json](v5_benchmark_summary.json), with the full narrative in
[the V5 report](../../comparison_new5_to_baseline_vn.md). Raw datasets/databases,
indexes, weights, generated predictions/traces and secrets remain excluded.
Staged-file checks found no prohibited artifact path or high-confidence secret token.
Personal scratch notes and unrelated presentation/binary documents remain local.

Development measurement HEAD was 663879a. The previous remote main was cebfeb1;
the publication merge retains that history while selecting the tested V5 tree,
without reintroducing the older main pipeline or rewriting remote history.
P6 remains the default/champion. Git publication is not a new accuracy experiment
or an A1 promotion decision.
