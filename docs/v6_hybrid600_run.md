# V4 incremental recovery on hybrid600MHz

> **Archived research after audit/rollback:** active checkout now uses measured
> V4 source on `v4_restored_after_v6_audit_20261016`. The V6 commands below are
> historical and are not compatible with the restored code. Do not execute them.
> [Audit and decision](../what_best_thing_to_do.md).

> **STOPPED — latest incident supersedes the running snapshots below.**
> `v6-hybrid600-full-20261016` stopped at Spider12/200 + Olist1/60 on
> GPU power84.55W >70W. Owned server/proxy/worker have closed cleanly.
> Do not run or resume this profile; preserve its latch and checkpoints.
> [Incident and separate CPU recovery plan](evidence/v6_hybrid600_power_stop_20261016.md).
> The CPU candidate has not run a model and requires post-incident pilot approval.

Branch `v6_v4_resilient`. Plan: [gates](v6_v4_incremental_plan_2026_10_16.md).
The user confirmed Administrator300–600MHzcap. Separateprofile
`qwen14b-hybrid-600-b8`:20GPUlayers+CPU8,8prompttokens/batch,sameQwen14Bweights,
context4096,≤3requests,600sdeadline,360sHTTPtimeout. Benchmarkbatch1,unload,60sactualcooldown,
continuousnative+WSLmonitoring,70W/68C/RAM8GiB/swap0.25GiB/VRAM14GiB unchanged.
Never change source,GitHEAD,model/config/indexes during run/resume; do not commit
even docs in this checkout. Oldstops/profiles/scores preserved. No guaranteedpower
oraccuracy improvement is inferred from partialoffload alone.

Architecture: V4question→sameV4draftprompt forbothbenchmarks; fixedschema/CTE/router;
existingbusinessglossarygrainmetadata; validation/read-onlyexecution;
question-onlyscalarcountshapecheck plusboundedmodelrepair for contradictoryoutput;
scopedCPUcount/rankedit or boundedoperationalrepair; strictincumbentselection.
No mandatoryextraLLMplan. Newvariant `v4-resilient`, opt-in; oldvariantsunchanged.
Newcountedit onlyonecatalogsource,oneboundgroup,COUNT(*),twooutputs,explicitmost/count
question,restrictedorderkeys; rejectsjoin/CTE/window/negation/ties/offset/ambiguous
metrics. ASTedit preserves allotherfields and admission matches exactcompiledSQL.

Offlinegate:makecheck336passed/1Ollamadeselected,Ruff/format306files,mypy123sources,
46.21s. Replay259contexts/251candidates:no newpolicyrejection/contextbudgetfailure;
8Olistviewcontextfixes,1readrouterfix,1CTEoldfailurelocal-equivalent. Counteditcorrects
oldolist020result,no priorcorrectcandidate becomesincorrect. This diagnoses savedSQL,
not newmodelaccuracy. Diagnosticfailures are developmentdata,not blindvalidation.

Initial180sdiagnostic `v6-hybrid600-diagnostic-20261016` cleanPAUSED after2successful
pilots; measured100sSpider/129sOlist. To reserve adequate CPUrepairtime, the final
profile uses bounded600s/case and360s/request; oldprofiles remain120/180s. Fresh
diagnostic `v6-hybrid600-cal2-20261016` uses2Spider+first6reorderedOlist,
max8batches then cleanPAUSED. Spider0499(priorpowerstop)and0795(oldCTEfailure);
Olist001(success),003(status),010(rawreviewaverage),020(count/rank),030(ordergrain),
032(oldgroundingfailure). Bothbenchmarks independentlypilot before remainingcases;
scoreonlyafterinference using separateevaluator. Do not open full if a resource/sensor
breach happens. All manifests,predictions,traces,reports ignored; never committed.

Fresh full command after diagnostics pass, using originalfullmanifests:

```bash
cd '/mnt/d/desktop_informations/vnpt ai/agentic_text_to_sql'
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks run \
 --name v6-hybrid600-full-20261016 --variant v4-resilient \
 --profile qwen14b-hybrid-600-b8 --models-dir /mnt/c/Users/ADMIN/.ollama/models
```

Monitor/manage the full sequence after it has started:

```bash
tmux attach -t v6-hybrid600-full-20261016
tail -f data/artifacts/experiments/v6-hybrid600-full-20261016/run.log
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks status --name v6-hybrid600-full-20261016
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks pause --name v6-hybrid600-full-20261016
# Wait for sequence PAUSED, then:
uv run --frozen --extra ui --group dev python -m scripts.tmux_benchmarks resume --name v6-hybrid600-full-20261016
```

Ctrl+b then d detaches withoutstopping. PerwrapperPAUSED aftereachcase is normal;
sequenceautomaticallycontinues. ResumeonlycleansequencePAUSED. Unexpectedreboot:
reapply600MHzcap,checkstalejobs/idle,thenresume--recovery-pilot; waitPAUSED before
normalresume. RESOURCE_STOPcannot be bypassed:preserveevidence,remediate,noretry.
Modelcompletion/accuracyremainIN_PROGRESS;actualdiagnostics/fullstatus appendedlater.

Deadline adjustment is based on measured CPU prefill latency, not a resource-limit
increase. Request/token count and model stay fixed. InitialSpiderpilotresult-correct;offlineOlistcheckrevealed SELECTorder_count from
customerfacts gives manyrows,not a scalarcount. This was caught before fullrun and
the broad Olistpromptchange was rejected. Firstdiagnostic retainedPAUSED; do not resume with newsource.
Newdeadlineverification and ≥5batchesstillrequired before fullrun.

Finalcalibration uses `v6-hybrid600-cal3-20261016` (freshidentity after reverting
Olistdraftformat toV4). Scalarcountshape check onlyunambiguous English/Vietnamese
countquestions,abstains for grouped/multiple-output wording; onecolumn/onerow is
required but never proves thevaluecorrect. Onshapecontradiction,skipcritic and spend
atmost the sharedrepairbudget; admitonly executable shapeconsistentcandidate.
Rawview-count regression reproduced in syntheticSQLite tests and alloldV4successes
checkedoffline:no newshapeviolations. Earliercal2 was operatorpaused afterSpider1,
ownedbackendclosed,withoutOlisttrial; not a safety/resource retry.

Finalcal4amendment: typeddeclaredrecordpopulation contracts check notonly outputshape
but countunit/sourcegrain. Olistbusinessglossary declares baseentityrelation/aliases
and boundedstatusvariants,never goldanswers/caseIDs/counts. Fullquestion matching
only; filter/join/groupingextrasnotdeclaredmustabstain. CPUcorrection matches exact
compiledSQL and passes samepolicy/executor; generalmodelrewriteisnotlicensed.
This recoverswrongsource/shapewithoutanextraLLMcall. The same namedtarget'scatalog
DDL is added if retrieval omittedit; promptbudget remainsenforcedwithouttruncation.
Cal3heldpausedafterSpider2+Olist1:Spider0499correct,Spider0795stillwrong,Olist001wrong
COUNTcustomerfacts. Hence nofullsuperiorityclaim; usefresh `v6-hybrid600-cal4-20261016`.
OfflineallV4replay: additionalrecordcontractcorrects003;count-rankcorrects020;zero
priorcorrectlosses ornewpolicy/shape/contextrejections. EarlierprovisionalV6handsoff
are superseded; finalsource/modelquality still needsactualcal4measurement.

## Latest actual execution

Finalsourcecommit `0fba637`; fullrun **hasstarted**, do not run `run` again.
Currentexperiment `v6-hybrid600-full-20261016`,originalSpider200+Olist60manifests,
no max-batches.8diagnosticbatches beforehandcompletedwithcleanunload/cooldown and
nohardware/sensorerrors;selectednew6/8vsV4 2/8,4gains/0losses. Two semanticfailures
remain; full accuracy unmeasured. Combinedobservedpower69.47Wnative/66.24Wguard,
temp58C,VRAM5460MiB,minRAM14.1946GiB;600MHzcaprespected. Nativepeakclose70W means
no guarantee ofnostops later. No thresholdrelaxation orautoretry. Modelgeneration
stillQwen14Bsameweights,context4096;hybridCPU20GPUlayers balancesload atmorelatency.
Evidence: [calibration](evidence/v6_hybrid600_calibration_20261016.md).

Keep this checkout atGitHEAD0fba637 andsource/config/model/indexes unchanged; live
handoff/evidencedocs are deliberatelyuncommitted untilfullcompletion. Monitor the
**full**session,not olderpauseddiagnostic orresource-stoppedV5sessions. Usepause,
waitsequencePAUSEDthenresume; detachCtrl+b,d keepsrunactive. RESOURCE_STOPrequires
actualremediation; resumeisnotanoverride. Check status/logs foractualprogress.

Handoffverified: **RUNNING atSpider2/200+Olist1/60**,nextSpiderbatchstarted,
bothfullpilotsverified,3fullbatchescheckpoint/unload/cooldowncomplete withoutsensor/
resource/cleanuperror. Including8diagnosticbatches=11cleanbatchesobserved. Allowned
PIDsalive,no stop/pausemarker,tmuxpanealive;source/settings/manifestschecked. Leave
jobrunning. Fullguardpeak66.88W;diagnosticnativepeak69.47W,sowatchdogremainsactive.
Actualprogresswilladvancepastthissnapshot;use status/logs. No fullaccuracyclaimyet.
