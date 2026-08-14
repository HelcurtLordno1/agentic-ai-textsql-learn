# Learning notes

Evidence-backed notes will be added gate by gate.

P6 makes dataset identity broader than one JSON checksum: a trustworthy release manifest must pin
the questions, schema metadata, and every executable database. Reordering full Spider dev by
database is a performance optimization only; retaining original `dev_index` and per-row hashes
keeps the selection auditable and makes a checkpointed prefix deterministic.

Execution accuracy is not one universal metric. Olist uses reviewed business semantics and explicit
tolerances; Spider tests cross-domain SQL equivalence. The UI therefore presents separate tabs and
never averages their scores. A portfolio report is also an API contract: detailed generated SQL is
useful locally for debugging but removed from the sanitized demo export.

Resource monitoring must sample independently from the inference process. P5.1 showed that manual
snapshots missed short power spikes; P6 keeps the same fail-closed supervisor around index builds
and release inference, and treats a preserved checkpoint as progress rather than a reason to weaken
the threshold.
