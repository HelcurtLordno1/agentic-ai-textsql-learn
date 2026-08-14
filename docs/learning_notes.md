# Learning notes

Evidence-backed notes will be added gate by gate.

P6 makes dataset identity broader than one JSON checksum: a trustworthy release manifest must pin
the questions, schema metadata, and every executable database. The laptop release combines a
domain-balanced regression-100 with a disjoint holdout-100, then reorders only for database reuse.
Retaining partition, original `dev_index`, and per-row hashes keeps selection auditable and makes a
checkpointed prefix deterministic. Full Spider-1034 remains an optional stronger-hardware profile.

Execution accuracy is not one universal metric. Olist uses reviewed business semantics and explicit
tolerances; Spider tests cross-domain SQL equivalence. The UI therefore presents separate tabs and
never averages their scores. A portfolio report is also an API contract: detailed generated SQL is
useful locally for debugging but removed from the sanitized demo export.

Resource monitoring must sample independently from the inference process. P5.1 showed that manual
snapshots missed short power spikes; P6 keeps the same fail-closed supervisor around index builds
and release inference, and treats a preserved checkpoint as progress rather than a reason to weaken
the threshold.
