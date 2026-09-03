# Repository instructions

- Treat `realistic_project_creation_codex.md` as the canonical specification and completion ledger.
- Work one roadmap gate at a time; do not mark a module `VERIFIED` without reproducible evidence.
- Runtime code must not import `agentic_text2sql_eval` or gold benchmark data.
- Keep the core local and free. Do not add paid provider SDKs or API-key requirements.
- Do not commit raw datasets, generated databases, indexes, traces, predictions, or secrets.
- Use typed contracts, bounded resource settings, and deterministic tests where possible.
- Run `make check` before claiming a gate complete.

## Laptop resource safety (mandatory)

- Never run a local-LLM benchmark or acceptance suite directly. Use its guarded wrapper with
  checkpointing, a batch size of 1, model unload between batches, and a cooldown.
- Before and during every local-model run, monitor available RAM, swap, VRAM, GPU temperature,
  GPU power, and utilization. Sampling only before/after a suite is insufficient.
- Local LLM requests must set an explicit bounded `TEXT2SQL_OLLAMA_NUM_GPU`; never leave GPU
  offload unbounded. Do not run generation and embedding models concurrently on this laptop.
- Refuse to start or stop immediately on a monitor failure or resource threshold breach. Preserve
  the last checkpoint, unload Ollama models, and report the observed reason/peak; never auto-retry
  a thermal, RAM, swap, VRAM, or power breach.
- Default long-run limits are conservative: at least 14 GiB available RAM, less than 0.25 GiB
  swap used, below 6 GiB VRAM, below 68 C GPU temperature, and below 70 W GPU power. Tighten these
  limits when the laptop is warm or not externally cooled; never loosen them without user consent.
- The only approved Qwen3-14B Olist exception is the `olist-paper1-ultrasafe` profile: one GPU layer,
  one case, 0.5-second sampling, 60-second cooldown, below 4 GiB VRAM, below 65 C, and a 78 W stop.
  This calibrated stop remains below the GPU manufacturer's 80 W default; it must not be reused for
  another model or workload without a new one-case pilot.
- If the Olist exception reaches its 78 W stop, do not resume it—even from a valid checkpoint—until
  an operating-system or NVIDIA Administrator hard clock/power cap is active and verified by a new
  one-case pilot. A software watchdog alone is not permission to oscillate at the stop threshold.
- After an unexpected shutdown, do not resume model work until all stale jobs are absent and an
  idle resource sample is safe. Run only a one-case guarded pilot before resuming a checkpoint.
