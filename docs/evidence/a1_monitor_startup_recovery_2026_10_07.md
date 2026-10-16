# Recovery from Windows monitor initialization timeout

The user requested continuation after `a1-monitorfix450-20261007` stopped at
Spider173/200 and Olist3/60. Stop evidence remains at the original report path.
Failure: `monitor failure: ValueError: Windows resource monitor startup timeout`.
Samples=0, observed_peak=null, cleanup_error=null; case174 was never spawned.
Native guardian has no resource latch, and server.log records clean native shutdown.
Root worker/server/proxy PIDs and suite child PID are null. No stale workloads were found
in WSL or Windows; the background Ollama server had no resident models, and owned ports
11435/11436 were free. This is an initialization failure, without evidence of a hardware breach.
The old log does not identify which initialization stage exceeded five seconds.

## Remediation

`windows_memory.ps1` caches the compiled native memory helper by its C# source SHA256
under `%LOCALAPPDATA%\AgenticText2Sql\monitor`. A manifest pins source and DLL hashes;
each new process validates both before loading. Compilation publishes the manifest last,
so interrupted compilation cannot publish an incomplete cache. Cached helper code still
uses GlobalMemoryStatusEx and EnumPageFilesW; resource calculations are unchanged.
Compiler/load initialization stages are recorded on stderr.
PowerShell supports creating and loading an assembly with `Add-Type`:
[Microsoft documentation](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/add-type?view=powershell-7.3).

Python startup readiness has a bounded15s window. No inference worker starts until
a valid fresh Windows sample exists. Running freshness remains1s, sampling0.5s,
and failures still stop without retry. Timeout now includes the initialization stderr stage.
Resource profile, 41GPUlayers, hardclock300–450MHz,180s case deadline, batch1,
model unload, cooldown60s, RAM/swap/VRAM/temperature/power limits all remain unchanged.

## Reproducible checks

- `make check`: Ruff/format279files and mypy119sourcefiles pass;
  260tests passed,1Ollama deselected,79.67s.
- New deterministic tests cover6s initialization followed by a fresh sample, unchanged
  1s running freshness, bounded15s initialization failure with diagnostic stage, and immediate
  sensor failure without retry.
- All5PowerShell scripts parse. Cold cache compilation and native RAM/pagefile reads pass.
- 12consecutive live monitor startups pass with verified cache reuse:0.4056–0.4279s.
- Idle monitoring60.013s plus startup samples:132samples, reason=null,
  RAMmin19.4190GiB,swapmax0.033978GiB,VRAM903MiB,temp52C,power22.78W,clock300MHz.

## Audited checkpoint continuation

Pre-edit source SHA matches both old frozen checkpoints:
`daec311d64316272e64a1ebb6eba1e9c2d824a7916cfbb21f43ca13572169c24`.
New source:
`b9f38c2260dece07a0b9f476ac284689a0b3e2e50a35aa65b367d2c785683193`.
Only2frozen source files changed: `windows_memory.ps1` and `windows_monitor.py`.
No added/removed frozen source files. New runtime identities differ only in source_sha256;
settings/profile/manifest/selection/DB/index/backend/model/template remain pinned.

Sequence `a1-startupfix450-20261007` copies the validated prefixes173/3 and backend
snapshots byte for byte. Old artifacts, source identities, logs and resource latch remain
untouched. Spider provenance records a startup_migration audit. Olist retains its frozen
evaluation_id. No completed case is rerun and no failure is removed from predictions.

Ignored evidence:
`data/artifacts/monitor-startup-recovery-20261007/{before.json,idle-and-startup.json,clone_checkpoints.py}`;
`data/artifacts/experiments/a1-startupfix450-20261007/startup-migration.json`.

The new sequence runs one guarded pilot for each benchmark with max-batches2, then
unload/cooldown and native cleanup. Full resume follows only after clean pilot evidence.
Research gate remains IN_PROGRESS; this recovery does not claim full completion or accuracy.

## Guarded pilots and full resume

| Pilot | Checkpoint | Status | RAM min GiB | VRAM max MiB | Temp max C | Power max W | Clock max MHz | Samples |
|---|---|---|---:|---:|---:|---:|---:|---:|
| spider_regression_0692 |174/200|SUCCEEDED|18.7626|9875|58|60.52|450|63|
| olist_acc_004 |4/60|SUCCEEDED|18.6355|9877|58|60.51|450|67|

Both journals have reason=null,cleanup_error=null,resource_stop=false,Windows RAM evidence,
swapmax0.037113GiB and sampleinterval0.5s. Root marks both pilots verified after clean
unload/cooldown60s. PAUSED174/200+4/60 has all worker/server/proxy PIDs null after native cleanup.
Original173/3 prediction prefix equality and original resource-stop latch preservation
were rechecked after pilots.

Full resume command has no totalmax-batches:

```bash
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume --name a1-startupfix450-20261007
tmux attach -t a1-startupfix450-20261007
```

The root runs the remaining Spider cases, then the remaining Olist cases, sequentially.
Completion requires `SUCCESS FINISH ALL: Spider 200/200 + Olist 60/60`, full reports,
and final native cleanup. Commands for status/pause/reboot recovery remain in
[the updated run plan](../monitor_recovery_plan_2026_10_07.md).

Handoff verification: first batch after full resume and server restart completed
`spider_regression_0694: SUCCEEDED`, checkpoint175/200; Olist4/60. Journalreason=null,
cleanup_error=null,resource_stop=false,69samples,peak60.51W/58C/9892MiB/450MHz.
Root remains RUNNING, suite COOLING after checkpoint/unload, tmux pane alive.
The remaining25Spider and56Olist cases continue automatically; full reports are pending.

## Final completion verified — 2026-10-08

The continuation finished Spider **200/200** and Olist **60/60**. Root and both suite
states are COMPLETE; cleanup_pending=false and all owned worker/server/proxy PIDs are
null. The final log contains `SUCCESS FINISH ALL: Spider 200/200 + Olist 60/60` and
`NATIVE SERVER CLEANLY STOPPED; job and runners closed`.

Final reports `a1-startupfix450-20261007-spider.json` and
`a1-startupfix450-20261007-olist.json` contain all pinned IDs and score **142/200**
and **41/60** respectively. Offline common-evaluator rescoring preserves every
correctness label. Current source digest matches both final runtime identities.
`make check` passes with 260 tests / 1 Ollama deselected, Ruff/format 281 files and
mypy 119 source files. No further model inference was run for this verification.

The [full current-code comparison report](../../comparison_new4_to_baseline_vn.md)
records paired baseline comparisons, failure diagnostics, latency, resource telemetry,
artifact lineage and research limitations. Completion of this workload does not promote
A1: its research gate remains IN_PROGRESS and P6 remains default/champion.
