"""Deterministic SQLite schema introspection without scanning table rows."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from agentic_text2sql.contracts.catalog import (
    CatalogSnapshot,
    ColumnInfo,
    ForeignKeyInfo,
    IndexInfo,
    TableInfo,
)


def readonly_sqlite_uri(path: Path) -> str:
    return f"file:{quote(str(path.resolve()))}?mode=ro"


class SQLiteIntrospector:
    """Capture tables, views, columns, composite FKs, and indexes in stable order."""

    def inspect(self, database: Path, db_id: str) -> CatalogSnapshot:
        connection = sqlite3.connect(readonly_sqlite_uri(database), uri=True)
        try:
            objects = connection.execute(
                "SELECT name, type FROM sqlite_master "
                "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            tables = tuple(
                self._inspect_object(connection, str(name), str(kind)) for name, kind in objects
            )
        finally:
            connection.close()
        canonical = json.dumps(
            [table.model_dump(mode="json") for table in tables],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return CatalogSnapshot(
            db_id=db_id,
            tables=tables,
            catalog_hash=hashlib.sha256(canonical.encode()).hexdigest(),
        )

    def _inspect_object(self, connection: sqlite3.Connection, name: str, kind: str) -> TableInfo:
        quoted = name.replace("'", "''")
        columns = tuple(
            ColumnInfo(
                name=str(row[1]),
                data_type=str(row[2] or ""),
                nullable=not bool(row[3]),
                primary_key_position=int(row[5]),
            )
            for row in connection.execute(f"PRAGMA table_info('{quoted}')")
        )
        grouped: dict[int, list[tuple[int, str, str, str]]] = defaultdict(list)
        for row in connection.execute(f"PRAGMA foreign_key_list('{quoted}')"):
            grouped[int(row[0])].append((int(row[1]), str(row[3]), str(row[2]), str(row[4])))
        foreign_keys = []
        for identifier in sorted(grouped):
            rows = sorted(grouped[identifier])
            foreign_keys.append(
                ForeignKeyInfo(
                    from_columns=tuple(row[1] for row in rows),
                    target_table=rows[0][2],
                    target_columns=tuple(row[3] for row in rows),
                )
            )
        indexes = []
        if kind == "table":
            for row in connection.execute(f"PRAGMA index_list('{quoted}')"):
                index_name = str(row[1])
                index_quoted = index_name.replace("'", "''")
                index_columns = tuple(
                    str(item[2])
                    for item in connection.execute(f"PRAGMA index_info('{index_quoted}')")
                    if item[2] is not None
                )
                indexes.append(
                    IndexInfo(name=index_name, unique=bool(row[2]), columns=index_columns)
                )
        return TableInfo(
            name=name,
            kind=kind,
            columns=columns,
            foreign_keys=tuple(foreign_keys),
            indexes=tuple(sorted(indexes, key=lambda item: item.name)),
        )
