"""Explicit human feedback storage; never auto-promotes examples."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from agentic_text2sql.contracts.trace import (
    FeedbackCategory,
    FeedbackRating,
    FeedbackRecord,
)


class SQLiteFeedbackStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS feedback (feedback_id TEXT PRIMARY KEY, "
                "run_id TEXT NOT NULL, rating TEXT NOT NULL, categories TEXT NOT NULL, "
                "note TEXT, created_at TEXT NOT NULL)"
            )

    def add(
        self,
        run_id: str,
        rating: FeedbackRating,
        categories: tuple[FeedbackCategory, ...] = (),
        note: str | None = None,
    ) -> FeedbackRecord:
        if rating is FeedbackRating.CORRECT and categories:
            raise ValueError("Correct feedback cannot include failure categories")
        record = FeedbackRecord(
            feedback_id=str(uuid.uuid4()),
            run_id=run_id,
            rating=rating,
            categories=categories,
            note=note.strip() if note else None,
            created_at=datetime.now(UTC).isoformat(),
        )
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT INTO feedback VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.feedback_id,
                    record.run_id,
                    record.rating.value,
                    ",".join(item.value for item in record.categories),
                    record.note,
                    record.created_at,
                ),
            )
        return record
