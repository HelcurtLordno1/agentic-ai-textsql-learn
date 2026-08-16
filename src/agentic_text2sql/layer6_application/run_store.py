"""SQLite run/event persistence with restart-safe reads and bounded payloads."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from agentic_text2sql.contracts.trace import RunRecord, RunStatus, TraceEvent


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SQLiteRunStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    db_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    config_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT
                );
                CREATE TABLE IF NOT EXISTS trace_events (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    layer TEXT NOT NULL,
                    event TEXT NOT NULL,
                    elapsed_ms REAL NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence)
                );
                CREATE INDEX IF NOT EXISTS idx_runs_updated ON runs(updated_at DESC);
                """
            )
            columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(runs)").fetchall()
            }
            if "config_json" not in columns:
                connection.execute(
                    "ALTER TABLE runs ADD COLUMN config_json TEXT NOT NULL DEFAULT '{}'"
                )

    def create(
        self,
        run_id: str,
        db_id: str,
        question: str,
        config: dict[str, object] | None = None,
    ) -> RunRecord:
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runs "
                "(run_id, db_id, question, status, created_at, updated_at, config_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    db_id,
                    question,
                    RunStatus.QUEUED.value,
                    timestamp,
                    timestamp,
                    json.dumps(config or {}, ensure_ascii=False),
                ),
            )
        return self.get(run_id)

    def set_status(
        self, run_id: str, status: RunStatus, result: dict[str, object] | None = None
    ) -> None:
        payload = json.dumps(result, ensure_ascii=False) if result is not None else None
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE runs SET status=?, updated_at=?, result_json=COALESCE(?, result_json) "
                "WHERE run_id=?",
                (status.value, _now(), payload, run_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown run: {run_id}")

    def update_config(self, run_id: str, values: dict[str, object]) -> None:
        record = self.get(run_id)
        merged = {**record.config, **values}
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE runs SET config_json=?, updated_at=? WHERE run_id=?",
                (json.dumps(merged, ensure_ascii=False), _now(), run_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown run: {run_id}")

    def recover_incomplete(self) -> list[str]:
        """Fail closed for work that cannot survive a process restart."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT run_id FROM runs WHERE status IN (?, ?) ORDER BY rowid",
                (RunStatus.QUEUED.value, RunStatus.RUNNING.value),
            ).fetchall()
        recovered = [str(row["run_id"]) for row in rows]
        for run_id in recovered:
            self.append_event(
                TraceEvent(
                    run_id=run_id,
                    layer="6",
                    event="APPLICATION_RESTARTED",
                    elapsed_ms=0,
                    details={"state": "FAILED"},
                )
            )
            self.set_status(
                run_id,
                RunStatus.FAILED,
                {
                    "run_id": run_id,
                    "status": "APPLICATION_RESTARTED",
                    "safe_message": "The local process restarted before this run completed.",
                },
            )
        return recovered

    def append_event(self, event: TraceEvent) -> TraceEvent:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM trace_events WHERE run_id=?",
                (event.run_id,),
            ).fetchone()
            sequence = int(row[0])
            created_at = _now()
            connection.execute(
                "INSERT INTO trace_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event.run_id,
                    sequence,
                    event.layer,
                    event.event,
                    event.elapsed_ms,
                    json.dumps(event.details, ensure_ascii=False),
                    created_at,
                ),
            )
        return event.model_copy(update={"sequence": sequence, "created_at": created_at})

    def events(self, run_id: str, after: int = 0) -> list[TraceEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM trace_events WHERE run_id=? AND sequence>? ORDER BY sequence",
                (run_id, after),
            ).fetchall()
        return [
            TraceEvent(
                run_id=str(row["run_id"]),
                sequence=int(row["sequence"]),
                layer=str(row["layer"]),
                event=str(row["event"]),
                elapsed_ms=float(row["elapsed_ms"]),
                details=json.loads(str(row["details_json"])),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def get(self, run_id: str) -> RunRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown run: {run_id}")
        return self._record(row)

    def list(
        self,
        *,
        limit: int = 50,
        status: RunStatus | None = None,
        query: str | None = None,
        include_result: bool = True,
    ) -> list[RunRecord]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        clauses: list[str] = []
        parameters: list[object] = []
        if status is not None:
            clauses.append("status=?")
            parameters.append(status.value)
        if query:
            clauses.append("question LIKE ? ESCAPE '\\'")
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parameters.append(f"%{escaped}%")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        parameters.append(limit)
        projection = (
            "*"
            if include_result
            else (
                "run_id, db_id, question, status, created_at, updated_at, config_json, "
                "NULL AS result_json"
            )
        )
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {projection} FROM runs{where} ORDER BY updated_at DESC LIMIT ?", parameters
            ).fetchall()
        return [self._record(row) for row in rows]

    @staticmethod
    def _record(row: sqlite3.Row) -> RunRecord:
        raw = row["result_json"]
        config = row["config_json"]
        return RunRecord(
            run_id=str(row["run_id"]),
            db_id=str(row["db_id"]),
            question=str(row["question"]),
            status=RunStatus(str(row["status"])),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            config=json.loads(str(config)),
            result=json.loads(str(raw)) if raw is not None else None,
        )
