# Research Paper 2 branch provenance

> **Current release: V5, 2026-10-17.** `best_research_v5` and the updated `main` publish
> the A1 `v4-reliability` CPU snapshot documented in [V5 reproduction](docs/v5_reproduction.md).
> Its development parent is `663879ab034dce1c604784a45504a03753926282`; the measured
> continuation source digest is `76a2c89a21778e0d0bed0812c9b5343bf366ec85b59e1b7020d60e76b761990a`.
> The previous remote main `cebfeb1fd1499c0fcb7f88634b594e2bf9b5135e` is retained as
> merge ancestry while the published tree uses the tested V5 runtime. Its older
> question-reliability implementation is not merged into the measured A1 pipeline.
> The Paper II narrative below is historical. P6 remains the default runtime pipeline.

> **Historical Paper II provenance:** active workspace is now P6 `baseline` at `0972e47`. This retained document describes the earlier research branch; DIN/semantic modules below are not installed in the active baseline. See [baseline transition record](docs/research_plan/baseline_transition_2026_10_01.md).

## Branch identity

- Branch: `research_paper2`
- Runtime baseline parent: `0972e4715f2aa8a64652c3b27d10c80f178bc162`
- Historical Olist result at that parent: `57/60` (`95.00%`)
- PRACTIQ archive branch: `practiq_paper1`
- PRACTIQ archive commit used for selected research documents:
  `e215356fa0f03807639e2c6818f339e5366d5ca7`

## Initial composition rule

At branch creation, runtime source, prompts, benchmark scripts, model configuration, Olist glossary,
and tests remained byte-for-byte at the `0972e47` tree. Only selected research documentation and the
mandatory laptop safety instructions were copied from `practiq_paper1` so the failed Paper I
experiment remained available as evidence for the next research direction.

The copied documents do not make the PRACTIQ implementation part of this branch. Reports describing
PRACTIQ are historical evidence, not a statement about the active runtime.

## Paper II development state

The branch now contains an independently implemented DIN-SQL research path. It is selected by
`TEXT2SQL_PLANNING_MODE=din_sql`; `baseline` retains the frozen v2/v4/v3 prompt path for paired
ablation. The implementation and deterministic evidence are documented in
`docs/evidence/r2_din_sql_implementation.md`. No Paper II accuracy result has been produced yet, so
the P6 baseline remains the champion and Gate R2 remains `IN_PROGRESS`.

## Safety boundary

The historical guarded runner at `0972e47` predates the later hardening and must not be used directly
for a local-model benchmark on this laptop. Before any model run, add or externally apply a guarded
orchestrator that meets `AGENTS.md`: batch size 1, continuous 0.5-second monitoring, explicit bounded
GPU offload, model unload, cooldown, checkpointing, and immediate stop on any monitor or resource
breach. Safety-only orchestration changes must be recorded separately from model/runtime changes.

Never reuse PRACTIQ predictions or splice its stopped prefix into a new evaluation. Every research
variant requires a fresh evaluation ID, prediction file, report, and provenance hashes.
