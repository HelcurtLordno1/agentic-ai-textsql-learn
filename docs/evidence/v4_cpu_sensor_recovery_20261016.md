# Persistent-sensor continuation

Plan: [§12](../../accurate_real_problem_set_plan.md). Parent
`v4-cpu600-stable-20261016` remains RESOURCE_STOP at44Spider+1Olist after
pre-spawn nvidia-smi timeout0.5s; samples0,peaknull,cleanup_errornull. No power
breach established in this incident. Both owned runtimes stopped cleanly.

make check341passed/1deselected,53.27s;Ruff316files,mypy121sources;nativePSparserpass.
PersistentGPU0stream200ms onWSL andWindows removes process-per-sample overhead,
with boundedstartup5s before inference,0.5s running waits/freshness,strictnumeric
validation,peak retention,EOF/stalefailclosed,andownedprocesscleanup. NativeGPU
sensor is assigned to the same kill-on-closeWindowsJob as the model server.

Model/prompt/policy/profile/settings/data/index unchanged. Explicitauditmigration
copies byte-identical44+1 predictions/backend to new experiment
`v4-cpu600-stream-20261016`; source changes limited to7monitor infrastructurefiles.
Old source b5e80887c0636c911119cc2feaf81f30cf881c52ea1109223205d6e886e60eab;
new76a2c89a21778e0d0bed0812c9b5343bf366ec85b59e1b7020d60e76b761990a;
HEAD663879ab034dce1c604784a45504a03753926282. Parentlatch/files unchanged.
Inheritedrows retainoldsource identity explicitly in continuation.json; newrows use
newsource. No inference/evaluation fabricated by migration. Oldstopnotresumed.

Dualidle240samples PASS (RAMmin20.956GiB,powermax23.9W,temp51C,WindowsRPCmax26.86ms);
nativeidle20samples onePID PASS. Source frozen before guardedcalibration/full.
S0/S1 VERIFIED; S2 calibration IN_PROGRESS, full not yet complete. Actualnew
sensor/resource stop still halts both; no automaticretry/thresholdincrease.

Localignored evidence: data/artifacts/v4-sensor-recovery-20261016/ and newexperiment
continuation.json. No raw data/index/trace/prediction committed.


Calibration completed cleanPAUSED48Spider+2Olist,allownedPIDsnull.5newguardedbatches/
1090samples,0stops/cleanuperrors,powermax31.23W,temp52C,RAMmin11.835GiB.
All23parenthashes/prefix44+1byteidentical. OfflineSpider36/48 vsV4same35/48;
Olist2/2vs2/2,1gain0334/0losses. Gaininherited,notcausalproof ofsensorfix.
Fullsequentialcontinuation requested,IN_PROGRESS. Source/HEADfrozen;noautoretry.


2026-10-17 user-requested cleanpause:96Spider/200+2Olist/60,allownedPIDsnull,
nativejob+runners+sensorclosed,no newlatches. Source/HEAD/parenthashes/prefix
unchanged. Do not autoresume;userwillresume tomorrow. Plan§12.8 includes normal
resume and one-case recoverypilot after reboot,retaining600MHzcap andsameprofile.
Finalpausehashes/statistics:local pause-handoff-96.json. Full remains IN_PROGRESS.
