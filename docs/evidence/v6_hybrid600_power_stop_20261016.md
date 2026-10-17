# V6 hybrid600 power stop and recovery plan

> **Subsequent decision:** the user rejected unproven latency/accuracy tradeoffs.
> V4 has been restored in the active checkout; the CPU candidate described below
> is archived and has never run inference. No CPU/full-run approval is pending
> as an active task. See [audit/decision](../../what_best_thing_to_do.md).

The previous running handoff is superseded: `v6-hybrid600-full-20261016`
is `RESOURCE_STOP`, at Spider **12/200** and Olist **1/60**. Git HEAD remains
`0fba637`. The next manifest case, not checkpointed, is
`spider_holdout_0119` (`car_1`, iteration 13).

The WSL watchdog recorded **84.55 W**, above the unchanged 70 W stop,
at 600 MHz. At the failed batch: temperature peak 54 C, VRAM peak 5448 MiB,
minimum available RAM 15.2801 GiB, maximum swap 0.070626 GiB; 89 observations,
maximum Windows memory RPC round trip 0.023137 s. Cleanup error is null.
`KeyboardInterrupt` occurred because the guard interrupted the HTTP generation
worker. There is no evidence here that an HTTP programming error caused the stop.

The native Windows journal did not capture the same transient (its maximum is
61.72 W). The samplers run at different times; that does not invalidate the WSL
observation or authorize ignoring it. The guard combines average and instantaneous
GPU readings with their maximum. Existing evidence cannot identify which of those
two fields contributed 84.55 W, nor prove an underlying electrical cause.

Runtime metadata confirms GPU layers 20, prompt batch 8, CPU threads 8,
case deadline 600 s, request timeout 360 s. Thus the intended hybrid settings
were applied; reducing GPU residency did not establish a reliable power bound.
The failed case is labelled easy in the manifest, so SQL difficulty alone is not
a sound explanation or a safe workload classifier. The prior 8 diagnostic cases
and the 13 full checkpoints were insufficient to qualify this profile for all
260 cases. No full accuracy/success-rate improvement has been established.

Post-stop checks: owned server/proxy/worker PIDs null, native server log says
the job and runners closed, no WSL benchmark/runner processes, tmux pane dead.
Only the pre-existing Windows Ollama app and idle server remain; no runner was
present. Three new dual-monitor idle samples: RAM >=20.3428 GiB, swap 0.0705033 GiB,
GPU 774 MiB, 47 C, <=18.04 W, 300 MHz. All were within the existing limits.
An idle sample is not permission to resume a breached workload.

## Recovery plan, before implementation

1. Preserve the entire experiment, checkpoint, resource latch and previous stops.
   Do not resume the hybrid600 experiment or raise/smooth/debounce the 70 W stop.
2. Prepare a separate **CPU-only** Qwen14B recovery profile. Keep the same model,
   V4-resilient SQL path, context, request/token budgets and 600/360 s bounds.
   Explicit `num_gpu=0`; use CPU-compatible f16 KV cache without flash attention.
   Keep CPU threads 8, prompt batch 8, batch one, unload, 60 s cooldown, all existing
   RAM/swap/VRAM/temperature/power limits and continuous dual monitoring.
   This removes CUDA inference load, but does not guarantee total GPU power or
   RAM/deadline safety; display/other applications still affect sensors.
3. Run deterministic checks, including the actual HTTP request hardware options.
   Do not launch inference without explicit post-incident pilot authorization.
4. After authorization, use fresh identities: one guarded case per benchmark,
   then the failed case and representative larger prompts/repair cases. Evaluate
   predictions offline against V4. Require at least five cooled iterations,
   measured RAM/power/latency and no known-success losses before considering full.
   Any new breach stops; no automatic retries. A short pilot is still not a proof
   of uninterrupted completion or higher full accuracy.
5. A fresh full run must use original manifests and a separately frozen source
   identity. Never append different settings to these 12+1 checkpoints. CPU
   execution will likely cost more time; if speed at 600–700 MHz is essential,
   a verified enforceable power limit is a separate hardware prerequisite,
   not a property that SQL architecture or clock locking alone can guarantee.

## Offline candidate verification

Implemented separate profile `qwen14b-cpu-recovery-b8`, explicit GPU0/CPU8/batch8,
f16 KV/no flash attention; same model selected by the unchanged V4-resilient
variant and unchanged resource/request/token/deadline bounds. The native Windows
launcher previously hardcoded flash attention/q8 KV regardless of profile. It now
receives explicit validated profile arguments. Existing hybrid/GPU profiles keep
their previous values; this launcher issue is not an explanation for the hybrid
power stop, since hybrid already specified those same values.

Mock HTTP transport verifies CPU generation really sends `num_gpu=0` with bounded
batch/context/output and keep_alive0. Native-launch boundary tests verify f16/no
flash arguments and unchanged RAM/swap/power limits without starting a model.
PowerShell syntax parser passes. `make check`: **370 passed, 1 Ollama deselected**,
45.90 s test runtime, Ruff/format314files and mypy126sources pass.
Audit log: `data/artifacts/v6-upgrade-20261016/cpu-recovery-make-check.log` (ignored).

Status: incident and offline preparation verified; **model calibration NOT RUN**.
No model request, checkpoint rewrite, latch deletion, threshold increase, Git
commit or automatic resume has occurred after the stop. The original run's Git
HEAD is unchanged, but the new candidate changes runtime source: old checkpoints
must not be resumed with these edits even without their resource latch.
Further model calibration requires explicit post-incident approval. CPU throughput,
RAM headroom, case completion and result correctness remain unmeasured.
