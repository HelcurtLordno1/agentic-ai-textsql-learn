import sqlite3
from pathlib import Path

from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector


def test_introspector_captures_composite_fk_view_and_stable_hash(tmp_path: Path) -> None:
    database = tmp_path / "catalog.sqlite"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        PRAGMA foreign_keys=ON;
        CREATE TABLE parent(a TEXT, b TEXT, PRIMARY KEY(a, b));
        CREATE TABLE child(
          a TEXT, b TEXT, value TEXT,
          FOREIGN KEY(a, b) REFERENCES parent(a, b)
        );
        CREATE INDEX idx_child_value ON child(value);
        CREATE VIEW child_view AS SELECT value FROM child;
        """
    )
    connection.close()

    introspector = SQLiteIntrospector()
    first = introspector.inspect(database, "test")
    second = introspector.inspect(database, "test")
    child = next(table for table in first.tables if table.name == "child")
    assert first.catalog_hash == second.catalog_hash
    assert child.foreign_keys[0].from_columns == ("a", "b")
    assert any(index.name == "idx_child_value" for index in child.indexes)
    assert next(table for table in first.tables if table.name == "child_view").kind == "view"
