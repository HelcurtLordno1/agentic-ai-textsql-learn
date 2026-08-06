"""Defense-in-depth read-only SQLite execution with hard resource caps."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote

from agentic_text2sql.contracts.validation import ResultPreview


class QueryTimeoutError(sqlite3.OperationalError):
    """Raised when SQLite's progress handler interrupts a query at its deadline."""


class ResultLimitError(sqlite3.OperationalError):
    """Raised when serialized results exceed the configured byte cap."""


DENIED_ACTIONS = {
    value
    for name in (
        "SQLITE_INSERT",
        "SQLITE_UPDATE",
        "SQLITE_DELETE",
        "SQLITE_CREATE_INDEX",
        "SQLITE_CREATE_TABLE",
        "SQLITE_CREATE_TEMP_INDEX",
        "SQLITE_CREATE_TEMP_TABLE",
        "SQLITE_CREATE_TEMP_TRIGGER",
        "SQLITE_CREATE_TEMP_VIEW",
        "SQLITE_CREATE_TRIGGER",
        "SQLITE_CREATE_VIEW",
        "SQLITE_DROP_INDEX",
        "SQLITE_DROP_TABLE",
        "SQLITE_DROP_TEMP_INDEX",
        "SQLITE_DROP_TEMP_TABLE",
        "SQLITE_DROP_TEMP_TRIGGER",
        "SQLITE_DROP_TEMP_VIEW",
        "SQLITE_DROP_TRIGGER",
        "SQLITE_DROP_VIEW",
        "SQLITE_ALTER_TABLE",
        "SQLITE_ATTACH",
        "SQLITE_DETACH",
        "SQLITE_PRAGMA",
        "SQLITE_REINDEX",
        "SQLITE_ANALYZE",
    )
    if (value := getattr(sqlite3, name, None)) is not None
}
UNSAFE_FUNCTIONS = {"load_extension", "readfile", "writefile", "fts3_tokenizer"}


class ReadOnlySQLiteExecutor:
    def __init__(
        self,
        *,
        timeout_seconds: float = 10,
        max_rows: int = 200,
        max_bytes: int = 2_000_000,
        progress_opcodes: int = 1000,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_rows = max_rows
        self.max_bytes = max_bytes
        self.progress_opcodes = progress_opcodes

    def execute(self, database: Path, sql: str) -> ResultPreview:
        started = time.monotonic()
        deadline = started + self.timeout_seconds
        uri = f"file:{quote(str(database.resolve()))}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only=ON")

        def authorizer(
            action: int,
            arg1: str | None,
            arg2: str | None,
            database_name: str | None,
            trigger_name: str | None,
        ) -> int:
            del database_name, trigger_name
            if action in DENIED_ACTIONS:
                return sqlite3.SQLITE_DENY
            function_name = arg2 or arg1 or ""
            if action == sqlite3.SQLITE_FUNCTION and function_name.lower() in UNSAFE_FUNCTIONS:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(authorizer)
        connection.set_progress_handler(
            lambda: 1 if time.monotonic() >= deadline else 0, self.progress_opcodes
        )
        try:
            cursor = connection.execute(sql)
            columns = [item[0] for item in cursor.description or ()]
            rows: list[list[object]] = []
            byte_count = 0
            truncated = False
            for row in cursor:
                if len(rows) >= self.max_rows:
                    truncated = True
                    break
                converted = list(row)
                byte_count += len(
                    json.dumps(converted, ensure_ascii=False, default=str).encode("utf-8")
                )
                if byte_count > self.max_bytes:
                    raise ResultLimitError("Serialized query result exceeded the byte cap")
                rows.append(converted)
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc).lower() or time.monotonic() >= deadline:
                raise QueryTimeoutError("Query execution exceeded its deadline") from exc
            raise
        finally:
            connection.set_progress_handler(None, 0)
            connection.set_authorizer(None)
            connection.close()
        return ResultPreview(
            columns=columns,
            rows=rows,
            truncated=truncated,
            elapsed_ms=(time.monotonic() - started) * 1000,
        )
