# CPU-only remediation after the 600 MHz power stop

The old experiment `v4-smallfix600b16-20261016` is RESOURCE_STOP atSpider30/200+
Olist1/60, not running. The next case0038 was interrupted before checkpoint.
The watchdog observed73.39W>70W at600MHz,56C,10103MiBVRAM;cleanup_error=null,
ownedPIDsnull,native job/runners cleanly stopped. Preserve23incident files;
`KeyboardInterrupt` was the guard stopping an HTTP request. No httpx patch or
threshold increase is used. Native `nvidia-smi.exe -pl60` was unsupported despite
exit0; no watt cap success is claimed.

[Plan§11](../../accurate_real_problem_set_plan.md) was written before code changes.
New profile `qwen14b-cpu600-stable` usesGPU0/CPU8/promptbatch64/f16/noFA,900s case/
300s request. SameQwen14Bweights,SQLite/A1pipeline/mechanicalpatches,prompts,context
4096,input2800/output768,max3requests. Keepgraphicscap600MHz,RAM>=8GiB,swap<0.25GiB,
VRAM<14GiB,temp<68C,power<70W,batchcase1,unload,60scooldown,dual0.5smonitoring.
Fresh experiment `v4-cpu600-stable-20261016`; no checkpoint/profile mixing.

`make check`:317passed/1Ollamadeselected,42.17s;Ruff/format311files,mypy120sources.
Tests verify actualHTTPGPU0/nativecachearguments,CPU-onlydeadlinebounds,heartbeat
through960s cleanup,oldGPUdefaults,read-onlydashboard/latchpriority/unknownstate/
completionreports and boundedviewport. Actualtmux integration found and fixed the
missing-target behavior of display-message; explicitwindowenumeration now prevents
respawning the wrong pane. Actualoldincidentmonitor remainsalive and reportsSTOP.
The monitor never runs inference/retries/clearslatches; workerexit status remainsreal.

Fiveguarded CPU batches reached cleanPAUSED4Spider+1Olist. Offline5/5correct vs
historicalV4same5/5,0gain/loss,1requesteach.1061guardsamples,max33.96W/52C,
RAMmin8.606GiB,VRAM~1142MiB;0sensor/resource/cleanuperrors. ActualAPIreportsQwen14B
size_vram0,context4096. CPUservice78–110s is an explicit slowdown for this recovery,
not an accuracy improvement or matched-profile speed claim. RAM margin to8GiB is
about0.6GiB in these pilots; guard remainsactive throughout full execution.

FullV4savedreplay repeated afterCPUcalibration:251prompts identical,249oldallowed
policydecisions/SQL unchanged,8emptycontexts recovered,1derived-outputcase local
correct;oldnestedaggregate230fullrows preserved. Evaluator opensgold onlyoffline
when inference isPAUSED; runtime never imports evaluator/gold.

Runtime sourceSHA frozen:
`b5e80887c0636c911119cc2feaf81f30cf881c52ea1109223205d6e886e60eab`.
GitHEAD663879a; source/config/HEAD not changed during inference. Backups,capability
checks,23incidenthashes,APIproof,prefixquality andpreflight local/ignored under
`data/artifacts/v4-stability-20261016/`.

FullCPU continuation requested afterfivecleaniterations; overallR2 remainsIN_PROGRESS.
Fiveprefixcases are exposed calibration evidence, not proof of completion, unseen
accuracy or no possible future failure. Actualbreach still stops both workloads
and preserves evidence; the independentmonitor displays the stopped state.

```bash
tmux attach -t v4-cpu600-stable-20261016
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks pause --name v4-cpu600-stable-20261016
# After cleanPAUSED only:
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume --name v4-cpu600-stable-20261016
```


### 11.9 Live handoff đã kiểm lại sau full batch đầu

SequenceRUNNING tạiSpider5/200+Olist1/60;6guardedbatches/1292observations hoàn tất,
0resource/sensor/cleanuperrors. Maxguard33.96W,minRAM8.606GiB. Firstfullcase0499
đãcheckpoint/unload/cooldown;batch kếtiếp đangchạy. Nămcalibrationcaseđãchấm5/5;
không tựgáncorrectness chocasefullchưachấm. Monitorpanealive/selected,ownedworker/
server/proxyalive,khônglatch/pausemarker,HEAD/sourcefreeze và23oldincidenthashes
unchanged. Snapshot `data/artifacts/v4-stability-20261016/live-handoff.json`.

Đây làtrạngtháiđangchạy đãquan sát,khôngphải fullCOMPLETE hoặc lời hứa khôngcó
lỗihardware/OS/resourcevềsau. Guardstopgiữnguyên vìan toàn;monitor độc lập giữ
khảnăngquan sát nếu cóstop. Người dùng dùngcommand§11.7;khôngresumeGPUexperimentcũ.
