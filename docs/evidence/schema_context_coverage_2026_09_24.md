# Schema Context coverage experiment — 2026-09-24

## Scope and source freeze

Qwen3-14B, model digests, prompts, correction limits and the default `legacy` schema mode were unchanged. This gate adds an opt-in `TEXT2SQL_SCHEMA_CONTEXT_MODE=coverage` strategy only. No runtime module imports benchmark gold or `agentic_text2sql_eval`. The implementation was frozen before opening aggregate holdout metrics; the only subsequent script changes handled empty BM25 retrieval and a relative output path. Neither changed either schema selector.

The strategy uses all tables, columns and declared foreign keys when they fit the fixed 1,200-token schema budget and six-table bound. On larger catalogs, it enumerates bounded FK closures of retrieved and lexical owner tables, keeps proven required owners/columns, and fills remaining budget with columns. A required owner that cannot fit produces a typed grounding error instead of silently disappearing. The default `legacy` path remains byte-equivalent in a deterministic test. This follows the testable idea in [The Death of Schema Linking?](https://arxiv.org/abs/2408.07702) for fitting schemas and the coverage/selection distinction in [CHESS](https://arxiv.org/abs/2405.16755). It is an implementation hypothesis, not a transferred paper result.

## Reproduction

```bash
make check
uv run python scripts/ablate_schema_context.py
uv run python scripts/ablate_schema_context.py --manifest evals/configs/spider-holdout-100.json
```

The script performs no Ollama calls. Both contexts are generated from the same BM25 top-20 retrieval and a question-only surrogate logical plan. It opens benchmark SQL only after both contexts have been frozen in memory. It prints aggregate numbers and writes no predictions. The raw Spider data and indexes remain local and uncommitted.

| Partition, 100 cases each | Mode | Micro table recall | Micro column recall | FK recall | Single-table contexts | Mean context tokens | Total linker time |
|---|---|---:|---:|---:|---:|---:|---:|
| Spider mini development | legacy | 0.575342 | 0.503448 | 0.025641 | 99 | 34.67 | 0.071 s |
| Spider mini development | coverage | 1.000000 | 1.000000 | 1.000000 | 0 | 185.71 | 0.222 s |
| Spider holdout, measured once | legacy | 0.569444 | 0.533074 | 0.081081 | 97 | 29.86 | 0.076 s |
| Spider holdout, measured once | coverage | 1.000000 | 1.000000 | 1.000000 | 0 | 169.19 | 0.211 s |

The full catalog happened to fit the 1,200-token/six-table bounds for these partitions. Therefore 1.0 recall is a direct consequence of inclusion, not evidence that the model chose correct SQL. Wider enterprise catalogs follow the bounded selection path, which has synthetic multi-schema tests but no measured cross-domain recall yet. The added prompt tokens may increase Qwen3 latency or distract generation; no execution-accuracy or p95 inference claim follows from this offline ablation.

`make check` passed Ruff, formatting, strict mypy on 115 source files, and 358 non-Ollama tests (one deselected). Model-free tests cover missing retrieval evidence, FK closure, anti-join population, budget rejection of proven owners, foreign index evidence and unchanged default mode.

## Promotion boundary

This is `IN_PROGRESS`, not `VERIFIED` or production ready. A paired guarded Qwen3-14B run with the same model digest, prompt, index, one GPU layer, correction budget and hardware profile must establish execution accuracy and latency before changing the default. On this laptop, the current idle sample was 22 GiB available RAM, no swap used, 1.097 GiB VRAM, 48 C, 18.27 W and 8% GPU utilization, with no stale Ollama job; the required Administrator graphics-clock lock for the Spider guard was not verified (idle clock 210 MHz, advertised max 1620 MHz). The guarded Spider launcher explicitly refuses a run without a verified 300–900 MHz hard cap. No local-model pilot or suite was started.
