# V4 incremental hybrid600 calibration and full-run handoff

> Subsequent full-run incident: **RESOURCE_STOP at Spider12/200 + Olist1/60**,
> GPU84.55W above70W. The clean calibration below did not establish full-run
> power safety. [Post-stop evidence and recovery plan](v6_hybrid600_power_stop_20261016.md)
> supersede the historical RUNNING handoff. No retry has been launched.

Final codecommit `0fba637`,branch `v6_v4_resilient`; runtime sourceSHA identical in
both suites:
`3843b851191de2d819f7fa3613e8423f0d9852eed72575a1e6b450288fa1df96`.
`make check`:367passed/1Ollamadeselected,Ruff/format312files,mypy126sources,44.82s.
No paidSDK/key,modelchange or benchmarkgold in runtime. Alloldstops/predictions/
reports remainunchanged; rawdiagnostics/data/predictions stayignored.

Retained V4questionfirstdraft onbothbenchmarks; retainedviewcolumn/CTE/readroutefixes.
No mandatoryLLMintent. Added exactscopedcount/rankCPUcontracts,question-onlyscalar
shapevalidation withboundedmodelrepair,and typedclosedrecordpopulation binding from
businessmetadata. Completecountquestionmustmatchdeclaredunit/filtervariant; catalog
ownership and base relation required; extra languageabstains. Queryrepair matches
compiledAST and passesexistingpolicy/read-onlyexecution. GeneralSQLsemanticsunproved.
OfflineV4replay:259contexts/251candidates,no newpolicy/shape/contextrejections;
8viewcontextrecoveries,003recordcounteditgain,020rankeditgain,no priorcorrectlosses.
These savedSQLchecks are not a new fullscore.

Resourcearchitecture is partitioned instead ofclock-onlyretry:Qwen3-14Bsameweights,
20GPUlayers,8prompttokens/batch,8CPUthreads,context4096,≤3generationHTTPattempts,
600scase/360srequestbounds. Deadlineincrease followed measuredCPU-prefill100/129s;
oldprofileskeep120/180s. Benchmarkbatch1,unload,cooldown≥60rawseconds; continuous
Windows+WSLguarding; RAM≥8GiB,swap<0.25GiB,VRAM<14336MiB,temp<68C,power<70W,
clock≤600MHz. User appliedAdministrator300–600MHzcap.700MHznotcalibrated here.

Earlypilotversionswereoperatorpausedcleanly tofixquality/deadlineissues,not retried
hardwarestops. Broad Olistprompt change was rejected after itcountedcustomerfacts
instead oforders. Scalarshapealone also missedthewrongcountunit. Finalmetadata
contracts address thatcase; all versions/sourceidentities/checkpoints keptseparate.

## Final diagnostic results — fresh inference, evaluator-only gold

`v6-hybrid600-cal4-20261016`:2Spider+first6reorderedOlist,8guardedbatches. Bothpilots
passed; all8SUCCEEDED/checkpointed/unloaded/cooled,noresource/sensor/cleanuperrors.
All8usedonegenerationrequest; no repairwasadmitted in these newpredictions. Gains
are integrateddraft/evidence/hardware outcomes,not proofCPUrepaircausedthegains.
CPUrepaircontracts were separately verified withsyntheticSQLite andsavedSQL replay.

| Case | V4 result-correct | New result-correct |
|---|---|---|
| spider_holdout_0499 (prior power-stop case) | yes | yes |
| spider_holdout_0795 | no | no |
| olist_acc_001 | yes | yes |
| olist_acc_003 | no | yes |
| olist_acc_010 | no | yes |
| olist_acc_020 | no | yes |
| olist_acc_030 | no | no |
| olist_acc_032 | no | yes |

**New6/8 vsV4 2/8,4gains/0losses** on deliberatelyselectedknowncases. This is
not blindvalidation or a statisticalguarantee thatfullSpider/Olist accuracy beats
V4 orP6baseline. Scope/CTEcase0795 andfreightgraincase030 remain semanticfailures.
Fullscores/promotionremainIN_PROGRESS. No benchmarkscorewasrewritten.

Continuous evidence:2466WSLguardobservations,3421nativeWindowssamples; combined
powerpeak **69.47W native** (66.24Wguard),temp58C,VRAM5460MiB,maxswap0.072064GiB,
minavailableRAM14.1946GiBguard/14.2022GiBnative,maxclock600MHz,maxmemoryRPC0.028790s.
Nativepowerpeak is close to70W; no claim of guaranteedfutureheadroom orstop-freefullrun.
Guards stayfail-closed; no thresholdincrease/autotry onactualbreach. All8cleanup_error
null. FinaldiagnosticsequencePAUSED atSpider2/Olist6,ownedPIDsnull,nativebackendclosed.

Full-launchgate requires8cleanbatches,alltypedSUCCEEDED,allscoredevaluationscomplete,
≥1gain/no priorcorrectloss in selectedsample,no stoplatches,sourceHEAD0fba637,
correcthybridsettings andfreshsafeidle. Gatepassed and started **fulloriginalmanifests**
`v6-hybrid600-full-20261016` with no max-batches,not the diagnosticmanifest. Runtime
source/model/settings/indexes frozen. Laterhandoffdocs remainuncommitted so GitHEAD
cannot invalidateSpiderprovenance. Operatorcommands in [run guide](../v6_hybrid600_run.md).

Ignoredaudits: `data/artifacts/v6-upgrade-20261016/{record-count-replay,cal4-scores,
final-calibration,full-launch-gate}.json`,final-make-check.log,plusindividualexperiment
native/guardjournals andruntimecheckpointfiles. Fullrunstatus appended afterpilots.

## Full session verified running at handoff

`v6-hybrid600-full-20261016` phaseRUNNING,cleancheckpointSpider2/200+Olist1/60;
nextSpiderbatchautomaticallystarted. Both fullpilotsverified.3fullbatchesSUCCEEDED,
checkpoint/unload/cooldowncomplete,noresource/sensor/cleanuperror,guardpowermax66.88W.
Togetherwithcal4thisis11cleanbatches (8diagnostic+3full),not a fullscore. Worker/
server/proxyPIDs verifiedalive,tmuxpane_dead=0,no pause-request/stoplatch. Both full
runtimeidentities match finalsourceSHA;GPU20/batch8/intentoff/resilientonverified,
original200/60manifestpathschecked. GitHEAD remains0fba637. The historical450MHz
powerstopcaseSpider0495passed in fullsecondbatch,guardpeak52.53W; prior0499passed
incalibration. Fullrunleftactive withnomaxbatches. Audit `full-handoff.json`ignored.
No further commits orsourcechangesduringrun;liveevidence/ledgerdocs uncommitted.
