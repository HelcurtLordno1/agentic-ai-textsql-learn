# Repository instructions

- Treat `realistic_project_creation_codex.md` as the canonical specification and completion ledger.
- Work one roadmap gate at a time; do not mark a module `VERIFIED` without reproducible evidence.
- Runtime code must not import `agentic_text2sql_eval` or gold benchmark data.
- Keep the core local and free. Do not add paid provider SDKs or API-key requirements.
- Do not commit raw datasets, generated databases, indexes, traces, predictions, or secrets.
- Use typed contracts, bounded resource settings, and deterministic tests where possible.
- Run `make check` before claiming a gate complete.

## Laptop resource safety (mandatory)

- Never run a local-LLM benchmark or acceptance suite directly. Use its guarded wrapper with
  checkpointing, a batch size of 1, model unload between batches, and a cooldown.
- Before and during every local-model run, monitor available RAM, swap, VRAM, GPU temperature,
  GPU power, and utilization. Sampling only before/after a suite is insufficient.
- Local LLM requests must set an explicit bounded `TEXT2SQL_OLLAMA_NUM_GPU`; never leave GPU
  offload unbounded. Do not run generation and embedding models concurrently on this laptop.
- Refuse to start or stop immediately on a monitor failure or resource threshold breach. Preserve
  the last checkpoint, unload Ollama models, and report the observed reason/peak; never auto-retry
  a thermal, RAM, swap, VRAM, or power breach.
- Default long-run limits are conservative: at least 14 GiB available RAM, less than 0.25 GiB
  swap used, below 6 GiB VRAM, below 68 C GPU temperature, and below 70 W GPU power. Tighten these
  limits when the laptop is warm or not externally cooled; never loosen them without user consent.
- The only approved Qwen3-14B Olist exception is the `olist-paper1-ultrasafe` profile: one GPU layer,
  one case, 0.5-second sampling, 60-second cooldown, below 4 GiB VRAM, below 65 C, and a 78 W stop.
  This calibrated stop remains below the GPU manufacturer's 80 W default; it must not be reused for
  another model or workload without a new one-case pilot.
- If the Olist exception reaches its 78 W stop, do not resume it—even from a valid checkpoint—until
  an operating-system or NVIDIA Administrator hard clock/power cap is active and verified by a new
  one-case pilot. A software watchdog alone is not permission to oscillate at the stop threshold.
- After an unexpected shutdown, do not resume model work until all stale jobs are absent and an
  idle resource sample is safe. Run only a one-case guarded pilot before resuming a checkpoint.

## User-authorized run profile — 2026-10-07

The user explicitly authorized hardware tuning and a new full run after the 6 GiB
VRAM stop, using the installed 16 GiB GPU and 32 GiB host. This supersedes the prior
pending-permission state. Use `qwen14b-16gb-clock-capped`: Qwen3-14B, bounded GPU
layers 41 (40 transformer blocks + output), RAM available >=8 GiB, swap/pagefile
<0.25 GiB, VRAM <14 GiB (2 GiB reserved), temperature <68 C, power <70 W, graphics
clock <=800 MHz. Keep batch=1, unload, cooldown >=60 seconds and continuous Windows
and WSL monitoring. Perform one pilot per benchmark, then run both sequentially.
Do not delete the prior run's stop evidence or silently mix profiles in a checkpoint.
This authorization covers the newly tuned run; sensor failures and subsequent actual
safety breaches still stop the workload and preserve evidence/checkpoints.

Full-offload pilot at the 800 MHz cap used 9705 MiB VRAM / 19.79 GiB available RAM,
but its instantaneous GPU power breached 70 W (peak81.2 W). Driver power-limit
setting is unsupported. Remediation keeps the same model/pipeline and full offload,
with an Administrator hard clock cap300–450 MHz and watchdog max450 MHz. Recalibrate
one guarded case per benchmark after the new cap is active; keep the 800 MHz stop
artifacts unchanged. The user explicitly requested planned fixes and full execution.

The new full-GPU profile uses a180-second case deadline (bounded by existing Settings
validation) to allow the unchanged request/token budgets at the lower clock. Default
profiles retain120 seconds. Administrator success is recorded in the ignored audit
`data/artifacts/gpu-clock-450.json`; verify450MHz during the guarded pilot.

## User-authorized 700 MHz profile — 2026-10-16

The user explicitly requested `nvidia-smi -i 0 -lgc 300,700` for the next V5 full run.
Use the separate `qwen14b-16gb-clock-capped-700` profile, watchdog maximum700MHz,
and new experiment/checkpoint paths. Keep the original450MHzprofile and all prior
stop/benchmark evidence unchanged. This authorizes only the clock increase: GPU41layers,
RAM>=8GiB,swap<0.25GiB,VRAM<14GiB,temp<68C,power<70W,deadline180s,batch1,
unload,cooldown>=60s and continuous Windows/WSL monitoring remain mandatory.
Apply the Administrator cap before starting; one guarded pilot per benchmark must
pass before the remaining workloads run sequentially. The700MHzconfiguration is
not yet calibrated by a model run. Actual sensor/resource breaches still stop and
preserve evidence without automatic retry/override; the prior800MHzpower breach
does not authorize raising the power stop.

## User-authorized 600 MHz remediation — 2026-10-16

The700MHzV5pilot breached the70Wlimit (71.11W at690MHz) and stopped cleanly;
its experiment/latch/evidence must remain unchanged. The user has now explicitly
chosen300–600MHz instead of the proposed450MHzremediation and reports Administrator
success for `nvidia-smi -i 0 -lgc 300,600`. Use a separate
`qwen14b-16gb-clock-capped-600` profile and fresh `v5-intent600-20261016` paths.
Only the clock maximum changes from the450MHzprofile; all other resource/model
limits remain unchanged. Verify stale jobs absent and safe idle before one guarded
pilot per benchmark, then continue fullSpider200+Olist60 sequentially. This is an
explicitly requested new calibration after hardware remediation, not permission to
retry an unchanged breached profile. Any new sensor/resource breach still stops
both workloads and preserves evidence without automatic retry or threshold increase.

## User-authorized 500 MHz remediation — 2026-10-16

The600MHzsequence stopped atSpider4/200+Olist1/60 after nativepower70.37W>70W.
The user now explicitly reports Administrator success for
`nvidia-smi -i 0 -lgc 300,500` and authorizes fresh fullSpider200+Olist60.
Use separate `qwen14b-16gb-clock-capped-500` and `v5-intent500-20261016` paths.
Preserve all600/700MHzstops and prior profiles; do not mix checkpoints. Only clock
maximum changes from450MHz; all model/resource/180sdeadline/batch1/unload/60scooldown
and continuous Windows/WSL monitoring remain unchanged. Require safe idle/no stale
jobs and independent guarded pilots before full sequential execution. Any actual
sensor/resource breach still stops both; no automatic retry or threshold increase.
Freeze Git HEAD before launch and do not commit even docs or move HEAD while running:
Spider provenance pins Git commit as well as runtime source/config identity. Keep
live handoff/evidence docs uncommitted until full run has finished cleanly.

## User-confirmed450MHzremediation — 2026-10-16

The500MHzV5sequence hit70.71W at495MHz onSpiderholdout0499 and stopped at4/200+1/60.
The user now reports Administrator success for `nvidia-smi -i 0 -lgc 300,450` and
explicitly requests full execution. Use existing `qwen14b-16gb-clock-capped` profile
(max450MHz),fresh `v5-intent450-20261016` paths and guardedpilots for bothbenchmarks.
Preserve500/600/700stops/checkpoints; do not mix profiles. Keep all other limits,
model/request budgets,batch1,unload,cooldown60s and continuous dualmonitoring.
Verify no stalejobs/safeidle before pilots; if safe, observe priorbreachcase0499.
Freeze Git HEAD throughout execution,including doc updates; actual resource/sensor
breaches still stop both and preserve evidence,without automatic retry/override.

## Batch16candidate after450MHzpower stop — pending explicit model-run approval

450MHzbatch64 also hit72.18W; do not resume it or auto-retry. A separate offline-tested
candidate `qwen14b-16gb-clock-capped-b16` lowers generationnum_batch64→16 only,
keepingGPU41,450MHz,allmodel/token/deadline/resourcebudgets,embeddingoptions,batch1,
unload/cooldown unchanged. This candidate is not powercalibrated. No modeltrial
has been authorized after the450MHzbreach yet; obtain explicit pilot/fullcontinuation
approval before using fresh v5-intent450b16-20261016 paths. Preserve all priorstops.

## User-authorized V4incremental hybrid redesign — 2026-10-16

The user explicitly changed the plan after450MHzpowerstop: develop incrementally from
V4,improve failure recovery and partition laptopcompute rather than retrying clocks;
Administrator600MHzcap confirmed. This authorizes the new softwarearchitecture,
guardeddiagnostics/pilots,≥5stableiterations and fullSpider200+Olist60 when gatespass.
Newcandidate `qwen14b-hybrid-600-b8` uses20GPUlayers,8promptbatchtokens,CPU8,
sameQwen14B/context4096/budgets/180sdeadline and existingRAM8GiB/swap0.25GiB/
VRAM14GiB/temp68C/power70W,batch1,unload,60scooldown,continuousWindows+WSLmonitoring.
Partialoffload is a testablehypothesis,not permission to ignore any newactualbreach.
Usefreshdiagnostic/fullpaths,preserveoldstops,and noautotryafternewresourcefailure.
No runtimegold/evalimports; scoreonlyoffline; noaccuracyguarantee beforepairedresults.
Freeze source/GitHEAD beforeinference;liveevidencedocs stayuncommitted throughout.

Initialhybridpilots bothpassed and were pausedcleanly at1Spider+1Olist,with no
resourcebreach. Measuredservice100s/129s leaves insufficientroomforhardcaserepair.
Use finalhybrid600sboundedcase deadline,360srequesttimeout; oldprofileskeep120/180s.
Token/request/model/resourcebudgetsunchanged. This is within user's accuracy/time
priority; requirefresh sourceidentity/diagnosticpaths `v6-hybrid600-cal2-20261016`.
Do not resume old180scheckpointwithchangedsettings/source. Fullpath remainsfresh.

Before fullrun, offlinequalitycheck caught Olist001 multirow-per-customer output in
broadguidedprompt. Finalresilientvariant returns to V4draftformat for bothsuites,
retains schema/scopefixes and adds boundedscalarcountshape-triggeredrepair,with no
runtimegold. Use fresh `v6-hybrid600-cal3-20261016` diagnostics; priorcal1/2stayPAUSED.
Noactualresourcebreach has occurred in hybridpilots; do not confuse operatorpause/
qualityiteration with resource-stopretry. Newactualbreach stillstops withoutretry.
