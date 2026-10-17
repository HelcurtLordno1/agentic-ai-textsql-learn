# Candidate450MHzgenerationbatch16 — no model trial yet

450MHzprofilebatch64 hit72.18W despite valid clock;70Wstop/latches remain unchanged.
Existing code sends generation `num_batch=64`; this is a prompt-token processing
batch, independent of benchmark batch1. Prepare separate
`qwen14b-16gb-clock-capped-b16` and fresh `v5-intent450b16-20261016` paths.
Typed HardwareProfile.ollama_num_batch defaults64,range1..256; existingprofileskeep64.
Candidate changes only name/description/generationnum_batch16. Qwen3-14B,GPU41,
context4096,input/output/request/deadline budgets,embeddingCPU/options,seed,unload,
benchmarkbatch1,cooldown60s and allresourcelimits unchanged. ExistingSettings handles
explicit environment value and generationHTTPpayload; provider/factoryprovenance
already read Settings. No embeddingcode/configchange.

Hypothesis: a smaller generationprompt-processingbatch may lower power bursts. This
is not a hardpowercap,not measuredremediation,not a claim of identicalSQLoraccuracy.
Power calibration still requires explicitly authorized guardedpilots after this
actual breach; no automatic retry or profile/latch override. Oldstops preserved.

Primary implementation reference: [Ollama llama_server batch arguments](https://github.com/ollama/ollama/blob/main/llm/llama_server.go)
passes NumBatch as-b/-ub. [NVIDIA SMI](https://docs.nvidia.com/deploy/nvidia-smi/index.html)
distinguishes clocklocking and powerlimits; localdiagnostic reports default80W and
power.limitN/A. These docs do not establish a guaranteedpowerreduction for thisGPU.

Offlinecodevalidation in progress. No Ollama inference,embedding or acceptancepilot
started for candidate. If user authorizes pilots+fullcontinuation on success, use:

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks run \
  --name v5-intent450b16-20261016 --variant intent-grounded \
  --profile qwen14b-16gb-clock-capped-b16 \
  --models-dir /mnt/c/Users/ADMIN/.ollama/models
```

This command is prepared, NOT EXECUTED. It auto-verifies oneguardedpilot perbenchmark
before fullsequentialexecution; model/resourcefailuresstillstopbothwithoutretry.
Freeze source/GitHEAD before authorizedtrial; keep subsequent docsuncommitted.

Offlinecodevalidation VERIFIED: `make check` Ruff/format296files,mypy122sources,
**319passed/1Ollamadeselected**,41.31s. Newtestsprove oldprofiledefaults64,same
model/resourcebudgets,boundedbatchvalidation,profileenv→Settings→HTTPgeneration16,
embeddingCPUoptionsunchanged,context4096/outputbudget/keep_alive0 preserved.
CLI accepts separatecandidate. SourceSHA `767a99cbb9989d0d526f2af0af99ea885efff5bf764aa74d418f0d36d26681d7`.
No modeltrialwasrun. Fullcalibration/accuracy/completion remain IN_PROGRESS.

Final450MHzcleanupchecked:allownedPIDsnull,nativejob/runnersclosed,oldapp3736only,
models=[].17continuousidle samples/10sSAFE,lastRAM20.6745GiB,swap0.071469GiB,
VRAM875MiB,temp48C,power17.10W,clock300MHz. Candidatepilotawaitsexplicitauthorization.
