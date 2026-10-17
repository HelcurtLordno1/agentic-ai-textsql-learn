# V5 700 MHz full-run preflight

User reports Administrator success for `nvidia-smi -i 0 -lgc 300,700` and authorizes
both full workloads, with observation of the first2–3iterations before handoff.

`make check`: Ruff/format293files,mypy121sourcefiles; **306 passed /
1 Ollama deselected**,41.85s. The monitor/heartbeat/cleanup/checkpoint tests pass.
All21indexes pass catalog/model/checksum/FAISS checks. Tested source SHA remains
`85d6b4eb34440b5991965bda16489ca37e3d40624c27e44c916a8ff913e7cb08`.
No stale benchmark/native runner exists; ordinary Windows Ollama0.30.10 is idle
(`/api/ps` models=[]). Both V5 experiment names are unused.

## Actual preflight clock failure

Before any model call, WindowsHostMonitor rejects a timestamp with age3157ms.
Raw transport capture shows a Linux CLOCK_REALTIME jump of3811.5ms while monotonic
advances233.1ms; native samples are252–270ms apart. `adjtimex` reports tick9000us,
frequency0; CLOCK_MONOTONIC runs about10%slower than CLOCK_MONOTONIC_RAW/Windows.
This is a host/guest timing problem; widening the1second freshness guard is not a fix.

Windows Time reports LeapIndicator3/not synchronized, Stratum0, LastSuccessfulSync
unspecified and Source=LocalCMOSClock. WSL systemd-timesyncd uses ntp.ubuntu.com
with an observed+3.582225s offset. This indicates competing/unaligned time references;
the exact process resetting tick still requires confirmation. A manual tick reset is
observed reverting to9000, including after stopping timesyncd; no permanent fix is claimed.

Temporary trials selected Hyper-V's shared-page clocksource, synchronized Linux to
Windows and reset tick10000. They did not pass fresh telemetry. The original tsc
clocksource and active/enabled systemd-timesyncd state were restored. No persistent
boot config changed and no model workload was started or retried.

Windows time resync requires Administrator: the current interop token receives
AccessDenied0x80070005. The user was asked to run `w32tm /resync /force` followed by
`w32tm /query /status` in the existing Administrator terminal. Model startup remains
held until a fresh continuous idle check passes; hardware thresholds are unchanged.

Artifacts stay ignored under `data/artifacts/v5-700-run-preflight-20261016/`, including
raw timestamp/tick traces and failed preflight summaries. These are not benchmark
predictions, not a safety-threshold retry, and not a new accuracy score.

Hyper-V time-source context: [Linux kernel clocks documentation](https://docs.kernel.org/virt/hyperv/clocks.html).
Observed WSL timing-conflict context: [Microsoft WSL discussion11548](https://github.com/microsoft/WSL/discussions/11548).
External reports do not establish this machine's exact cause; the local measurements
above are the evidence for holding model startup.

## Clock-independent protocol remediation

Implemented `text2sql-memory-rpc-v2`: each RAM/pagefile read is initiated by one
random request ID and accepted only once, with round trip and delivery bounded to
1 second of `CLOCK_MONOTONIC_RAW`. The Windows helper reads native sensors after
receiving that ID; it does not return a cached sample. Missing, delayed, malformed,
replayed or mismatched responses fail closed. Host Unix time remains an audit field;
its agreement with guest UTC is no longer a freshness dependency. Bootstrap remains
15 seconds, with no model work until a valid response arrives.

Native Ollama ownership now uses an append-counter heartbeat. Windows Stopwatch
measures lack of counter progress against the existing10second stop, independent of
Linux file mtimes. Request deadlines, execution timing, guard intervals and cooldown
use raw elapsed time; cooldown still lasts at least60actual seconds. Resource limits,
stop latches, model settings and inference architecture are unchanged.

Continuous idle validation: **SAFE**,60.354actual seconds,119samples; maximum memory
RPC round trip0.025763s. Minimum host/WSL RAM20.0548GiB; max swap/pagefile0.076485GiB,
VRAM730MiB,temp52C,power23.55W,clock300MHz (idle; load calibration is still required).
Artifacts: `idle-rpc-v2.json` and `idle-rpc-v2.samples.json` in the ignored preflight
directory. PowerShell parser accepts all Windows scripts. Focused34tests pass before
full-suite validation, including stale/replayed/missing telemetry and elapsed-time
budgets despite host-time differences. Earlier failed idle evidence remains intact.

Final `make check` after remediation: Ruff/format296files,mypy122sourcefiles;
**315 passed /1Ollama deselected**,100.11s. Native heartbeat regression test also
passes in the focused8test sequence suite. No LLM was invoked by these checks.
Final source SHA before launching fresh inference:
`ee81930a85315c7fba287b19b922f76d27d22b16c9a2d455d1cba66f2ce39aea`.
The monitor remediation gate is VERIFIED for deterministic checks and live idle
telemetry.700MHzmodel calibration and full accuracy measurement remain pending.

## Actual guarded700MHzpilot: hardware power stop

Code commit `8d4756f` was frozen and full sequence `v5-intent700-20261016` launched
without a max-batches limit. The harness started its guarded Spider pilot; before a
case completed, sampled GPU power reached **71.11W**, exceeding the unchanged70W
limit. The guard stopped inference, unloaded models and completed cooldown. This is
an actual power breach, not the previous timestamp/monitor error. The displayed
`KeyboardInterrupt` is the consequence of guard termination, not an independent
Python import defect.

Pilot observations:70samples at0.5s; minavailableRAM19.3655GiB,maxswap0.077843GiB,
VRAM9725MiB,temp56C,power71.11W,clock690MHz. Fresh Windows memory RPC max0.024435s;
cleanup_error=null. Thus the clock cap was respected while the power threshold was
not. A graphics clock cap does not by itself certify the requested power envelope.

Final sequence phase RESOURCE_STOP; checkpoints Spider0/200,Olist0/60; no pilot
passed and no full accuracy result exists. Worker/server/proxy PIDs are null. Native
server log confirms `NATIVE SERVER CLEANLY STOPPED; job and runners closed`.
Evidence remains ignored in the experiment directory and
`evals/reports/v5-intent700-20261016-spider.resource-stop.json`. Do not delete the
latch or resume this700MHzexperiment, and do not reuse its name to bypass the stop.

Next execution requires actual hardware remediation. The current interop token lacks
Windows Administrator privileges; the user was asked to apply300–450MHzhard cap in
Administrator PowerShell. After confirmation, use a separate450MHzprofile/name,
check safe idle and stale-job absence, then independently pilot Spider and Olist
before continuing both full suites. Prior450MHzV4calibration does not certify V5.
Until that external action arrives, no further local-model request is authorized by
this stop handling. Source verification is complete; full-run calibration remains
IN_PROGRESS. No claim of2–3stable iterations or full completion is made.

Post-stop verification:15continuous idle samples over10seconds are safe; lastRAM
20.8201GiB,swap0.075386GiB,VRAM726MiB,temp48C,power17.87W,clock300MHz. Native
process enumeration shows only the user's pre-existing Ollama app serverPID3736;
ownedPID19024 and model runners are absent. Its `/api/ps` reportsmodels=[]. Saved
in ignored `after-power-stop-idle.json`. Fresh450MHzsequence paths remain unused.
