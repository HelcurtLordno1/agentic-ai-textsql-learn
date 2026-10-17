# V4 incremental recovery and laptop execution plan

Latest status: hybrid600 full run stopped on measured84.55W>70W atSpider12/Olist1.
The historical calibration gates below do not certify uninterrupted execution.
See [incident/recovery plan](evidence/v6_hybrid600_power_stop_20261016.md).
CPU-only candidate is an offline preparation, not an authorized model retry.

User changes scope: develop from measured V4, prefer high result accuracy over raw
speed, hard cap600MHz already applied; authorize new architecture/calibration,
selected failure tests, ≥5stable batches and fullSpider200+Olist60 if gates pass.
No permission to raise70W or auto-retry an actual hardware/sensor breach. Preserve
V4 remote/scores and all800/700/600/500/450stops. This plan precedes implementation.

G1 — retained V4 draft path and bounded independent CPU recovery:
- No mandatory pre-SQL LLM plan; first generation uses original question/schema.
- Keep view-column packing, lexical SQL scopes, metadata read-route fixes.
- Olist-only concise grain/population guidance in draft, no domain assumptions added
  to other databases. Keep explicit intent variants for separate research controls.
- Extend scoped AST recovery only for unambiguous simple grouped counts with explicit
  cardinality and ranking instructions. Bind count/group/source independently; preserve
  population,projections,joins,predicates,metric,tiekeys; no unrestricted semantic edits.
- Preserve operational model repair and≤3requests/180s; no gold/runtime imports.
G2 — resource partition, not clock escalation:
- Newidentity600MHz,20GPUlayers,8prompttokens/batch,8CPUthreads; same Qwen14Bweights,
  context4096,request/tokenbudgets,batch1,unload,cooldown≥60s,existing70W/68C/RAM8GiB/
  swap0.25GiB/VRAM14GiB. Partial offload is a hypothesis to reduce concentrated GPU
  load,not a power guarantee. More CPU work may increase latency; measure deadline.
- No concurrent embedding/generation, all guarded with continuous native+WSL sensors.
- Freeze source+HEAD before inference; no commits during pilots/fullrun.
G3 — deterministic evidence:
- makecheck; saved V4 contexts/policy replay; evaluate all proposed deterministic
  repairs against saved V4 outcomes offline, including every priorcorrect candidate.
- Realistic synthetic tests for abstention,scopes,ties,projection invariants,repair
  admission and HTTPhardwareoptions. No successfulcase lookup in runtime.
G4 — guarded calibration/research execution:
- Fresh paths; idle/stale checks,onepilot perbenchmark,then diagnostic selected V4
  failures and successes (report diagnostic not blind evaluation). Runtime only sees
  question/database/catalog; gold stays evaluator-only. No hardcoded answers.
- Require ≥5cooled batches, inspect power/memory/CPUtiming and paired sample outcomes,
  including cases previously powerstopped. Full run only after initial gates pass;
  if any breach:stop,unload,cool,preserve evidence,no auto-retry.
- Accuracy promotion requires full paired V4/new result comparison. A small pilot
  cannot establish confident superiority, and executability is not resultcorrectness.

Current gate G1 IN_PROGRESS. All modelruns stopped; no new inference launched.

Measured amendments before full run:
- Hybridprefill100/129s on firstpilots requires600sboundedcase/360srequest for repair;
  oldprofilesremain120/180s. User prioritizesaccuracy overduration. No resource change.
- Rejected broad Olistdraftprompt replacement after offlinequalitycheck caught a
  scalarcountregression. Finalvariant retainsV4draftformat on bothbenchmarks with
  fixedschema/domainmetadata. Add narrow question-onlyscalarcountshapevalidation and
  boundedmodelrepair,abstaininggrouped/multiple-outputquestions. Shapeconsistent is
  necessary,not proof ofcorrectvalue. Finalcal3freshpaths; no oldcheckpointrewrite.

Cal3 exposed a one-cell wrong-grain result too (COUNTcustomers for countorders),
confirming shapecheckalonecannotprotectsuccesses. Final increment: a typed,closed
RecordCountGoal binds the complete countquestion to existing domainentity metadata,
a catalog base relation and≤2declaredfilters. No IDs,goldSQL,expectedrows or counts
are stored. Unknown/extraphrases abstain. Originaldraft is kept when consistent;
otherwise a CPUquerycontract licenses exactly its compiledCOUNT query,stillpolicy/
executionchecked. This covers basic counts/statuscounts; generalSQL remainsmodel-led.
Freshcal4diagnostics required; previousversionspausedcleanly,nevermixedcheckpoints.
