# R1 local-model resource incident and guard evidence

Status: `GUARD_REQUIRED`; benchmark promotion blocked
Date: 2026-08-31 (Asia/Bangkok)

## Incident

The laptop unexpectedly shut down while the R1 reliability benchmark was running against local
Ollama. The old runner sampled resources only at suite boundaries and inherited
`TEXT2SQL_OLLAMA_NUM_GPU=None`, so the request did not impose an explicit GPU-offload bound. It also
had no in-flight thermal/power/RAM circuit breaker. The exact pre-shutdown peak is unavailable because
the operating system stopped before it could be checkpointed; attributing one specific sensor as the
sole cause would therefore be unsupported.

The JSONL checkpoint survived with 22 valid v5 records. No partial line was present and the recorded
prediction SHA-256 is
`1492efa8a942c3750f4b44e7b48283807a47780bc26e08fc1d1cfa58c00da9de`.

## Permanent controls

- `AGENTS.md` now prohibits direct local-LLM benchmark/acceptance runs.
- `ProfileName.R1_RELIABILITY` fixes one case per batch, four GPU layers, six CPU cores, one loaded
  model, unload after each batch, and at least 45 seconds cooldown.
- Hard limits: available RAM >=14 GiB, swap <0.25 GiB, VRAM <6,144 MiB, GPU <68 C, GPU power <70 W.
- `scripts/run_guarded_r1_reliability.py` samples every 0.5 seconds, preserves the per-case checkpoint,
  interrupts the benchmark, unloads the model, and exits 75 on a resource breach or monitor failure.
- `scripts/serve_ollama_guarded.py` independently monitors and stops the Ollama process group using
  the same profile, providing two circuit-breaker layers.
- A thermal/resource breach is never retried automatically and limits cannot be loosened without user
  consent.

## Reboot recovery and circuit-breaker trial

Idle sample before retry: 22.64 GiB available RAM, zero swap, 579 MiB VRAM, GPU 51 C and 20.17 W.
The Windows Ollama model store was mounted read-only as the model source for the guarded WSL server.

Exactly one resumed case was attempted. Both guards stopped the workload at the same threshold:

```json
{
  "status": "resource_guard_stop",
  "reason": "GPU power 72.0 W",
  "checkpoint": 22,
  "peak": {
    "available_ram_gib": 22.256820678710938,
    "swap_used_gib": 0.0,
    "gpu_memory_mib": 2274,
    "gpu_temperature_c": 59,
    "gpu_power_w": 72.02,
    "gpu_utilization_pct": 96
  }
}
```

The checkpoint remained 22/100, proving fail-closed behavior before an unsafe run could continue.
Post-stop idle state returned to 52 C, about 579 MiB VRAM, 20.23 W, and 22 GiB available RAM.

## Verification

`make check` completed without Ollama: Ruff and formatting passed, strict mypy passed for 110 source
files, and 208 tests passed with one Ollama-marked test deselected. Unit coverage asserts that the R1
profile cannot silently exceed the documented limits.

The full 100-case accuracy report is intentionally not fabricated. Resumption requires an explicitly
approved hardware strategy that can remain below the 70 W power breaker (for example a smaller local
model with a separately versioned benchmark, or externally cooled execution).

## Olist Qwen3-14B calibrated follow-up

At the user's explicit request to retain Qwen3-14B accuracy, an Olist-only profile was calibrated to
one GPU layer with a 78 W stop (below the GPU manufacturer's 80 W default), a tighter 65 C thermal
stop, 4 GiB VRAM ceiling, one-case batches, 0.5-second sampling, unload, and 60-second cooldown.
Independent pilots completed at 63–64 C and 75.08–77.01 W with zero swap. The locked Olist-60 v1
attempt then stopped at checkpoint 5/60 on a 78.68 W breach. This establishes that a watchdog alone
cannot safely finish the suite; a verified Administrator-level hard clock/power cap is now required.
