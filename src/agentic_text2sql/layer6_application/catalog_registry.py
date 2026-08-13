"""Server-side registry for approved database identifiers and immutable catalog snapshots."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector


class CatalogRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS catalogs (db_id TEXT PRIMARY KEY, database_path TEXT "
                "NOT NULL, catalog_json TEXT NOT NULL, registered_at TEXT NOT NULL "
                "DEFAULT CURRENT_TIMESTAMP)"
            )

    def register(self, db_id: str, database: Path) -> CatalogSnapshot:
        if not db_id or not db_id.replace("-", "_").isalnum():
            raise ValueError("db_id must contain only letters, numbers, underscore, or hyphen")
        resolved = database.resolve(strict=True)
        if resolved.suffix.lower() not in {".sqlite", ".db"}:
            raise ValueError("Only SQLite .sqlite/.db files can be registered")
        catalog = SQLiteIntrospector().inspect(resolved, db_id)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT INTO catalogs(db_id, database_path, catalog_json) VALUES (?, ?, ?) "
                "ON CONFLICT(db_id) DO UPDATE SET database_path=excluded.database_path, "
                "catalog_json=excluded.catalog_json, registered_at=CURRENT_TIMESTAMP",
                (db_id, str(resolved), catalog.model_dump_json()),
            )
        return catalog

    def resolve(self, db_id: str) -> tuple[Path, CatalogSnapshot]:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT database_path, catalog_json FROM catalogs WHERE db_id=?", (db_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown database id: {db_id}")
        path = Path(str(row[0]))
        if not path.is_file():
            raise FileNotFoundError(f"Registered database is unavailable: {db_id}")
        return path, CatalogSnapshot.model_validate_json(str(row[1]))

    def list(self) -> list[CatalogSnapshot]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute("SELECT catalog_json FROM catalogs ORDER BY db_id").fetchall()
        return [CatalogSnapshot.model_validate_json(str(row[0])) for row in rows]
