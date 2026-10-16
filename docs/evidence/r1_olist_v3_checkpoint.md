# Olist Paper-I v3 paused checkpoint

Status: `PAUSED`, not a completed benchmark and not gate evidence.

## Saved state

- Evaluation ID: `olist-paper1-r1-60-v3`
- Completed predictions: `28/60`
- Last completed case: `olist_acc_028`
- Next case on resume: `olist_acc_029`
- Terminal statuses saved: 27 `SUCCEEDED`, 1 `VALIDATION_FAILED`
- Prediction SHA-256 at pause: `dd125768a0d71dfdeea0a93786209349ba091cae79f871ea9c6dbfb5215a2a2b`
- Source snapshot: verified against `olist-paper1-r1-60-v3.provenance.json`
- Observed guarded-run peak through case 28: 51.4 W GPU power, 59 C GPU temperature,
  2,593 MiB VRAM, 600 MHz graphics clock, 0 GiB swap.
- The benchmark was interrupted during the post-case cooldown. No partial case was appended.
- Ollama, its runners, and the acceptance process were stopped after saving the checkpoint.

The incomplete JSONL must not be evaluated or reported as final accuracy. One terminal result is a
validation failure, but correctness and the final failure set are intentionally deferred until all 60
cases exist.

## Safe resume procedure

Do not change any file listed in the provenance `source_snapshot`. If a listed hash changes, start a
new evaluation ID and a new prediction file instead of mixing results.

After an idle resource preflight, reapply the NVIDIA Administrator graphics-clock lock at 300--600
MHz and verify it with a new guarded one-case pilot as required by `AGENTS.md`. Then start the guarded
server:

```bash
.venv/bin/python scripts/serve_ollama_guarded.py \
  --profile olist-paper1-ultrasafe \
  --sample-seconds 0.5 \
  --models-dir /mnt/c/Users/ADMIN/.ollama/models
```

In another terminal, resume the existing checkpoint (resume is the default):

```bash
.venv/bin/python scripts/run_guarded_acceptance.py \
  --profile olist-paper1-ultrasafe \
  --predictions evals/predictions/olist-paper1-r1-60-v3.jsonl \
  --report evals/reports/olist-paper1-r1-60-v3.json \
  --evaluation-id olist-paper1-r1-60-v3
```

The first message must say `resuming after 28/60 persisted predictions`; the next inference must be
`olist_acc_029`. Stop immediately if either condition is false. Keep batch size 1, the 60-second
cooldown, model unloads, and all profile thresholds unchanged.

After the complete run, stop Ollama, restore the NVIDIA graphics clock with Administrator
`nvidia-smi.exe -rgc`, run the evaluator-generated report checks, and run `make check` before changing
the roadmap ledger.
