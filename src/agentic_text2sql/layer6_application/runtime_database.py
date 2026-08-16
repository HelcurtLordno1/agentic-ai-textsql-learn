"""Atomic WSL-native read-only database staging for low-latency local execution."""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from pathlib import Path


def stage_runtime_database(source: Path, cache_root: Path, db_id: str) -> Path:
    """Reuse an immutable local cache identified by source metadata without mutating the source."""
    resolved = source.resolve(strict=True)
    stat = resolved.stat()
    identity = hashlib.sha256(
        f"{resolved}\0{stat.st_size}\0{stat.st_mtime_ns}".encode()
    ).hexdigest()[:16]
    target_root = cache_root.resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    db_key = hashlib.sha256(db_id.encode()).hexdigest()[:8]
    target = target_root / f"database-{db_key}-{identity}.sqlite"
    if target.is_file() and target.stat().st_size == stat.st_size:
        return target

    temporary = target_root / f".{identity}.{os.getpid()}.{uuid.uuid4().hex}.staging"
    try:
        shutil.copyfile(resolved, temporary)
        if temporary.stat().st_size != stat.st_size:
            raise OSError("runtime database staging produced an incomplete copy")
        current = resolved.stat()
        if (current.st_size, current.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
            raise OSError("source database changed while runtime copy was staged")
        temporary.chmod(0o400)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
