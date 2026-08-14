"""Stable decoding for legacy SQLite TEXT values containing malformed UTF-8."""

from __future__ import annotations


def decode_sqlite_text(value: bytes) -> str:
    """Return JSON-safe text while preserving valid UTF-8 and marking malformed bytes."""
    return value.decode("utf-8", errors="replace")
