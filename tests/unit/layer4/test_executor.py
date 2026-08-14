import hashlib
import sqlite3
from pathlib import Path

import pytest

from agentic_text2sql.layer4_validation.executor import (
    QueryTimeoutError,
    ReadOnlySQLiteExecutor,
    ResultLimitError,
)


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "database.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE values_table(value TEXT)")
    connection.executemany("INSERT INTO values_table VALUES (?)", [("x" * 20,)] * 20)
    connection.commit()
    connection.close()
    return path


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_read_execution_preserves_database_checksum(database: Path) -> None:
    before = checksum(database)
    result = ReadOnlySQLiteExecutor(max_rows=5).execute(database, "SELECT * FROM values_table")
    assert len(result.rows) == 5
    assert result.truncated
    assert checksum(database) == before


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM values_table",
        "CREATE TABLE evil(x)",
        "PRAGMA user_version",
        "ATTACH DATABASE '/tmp/evil.db' AS evil",
        "SELECT load_extension('evil')",
    ],
)
def test_executor_defense_in_depth_denies_mutation(database: Path, sql: str) -> None:
    before = checksum(database)
    with pytest.raises(sqlite3.DatabaseError):
        ReadOnlySQLiteExecutor().execute(database, sql)
    assert checksum(database) == before


def test_timeout_interrupts_expensive_query(database: Path) -> None:
    sql = (
        "WITH RECURSIVE counter(x) AS (VALUES(1) UNION ALL "
        "SELECT x + 1 FROM counter WHERE x < 100000000) SELECT SUM(x) FROM counter"
    )
    with pytest.raises(QueryTimeoutError):
        ReadOnlySQLiteExecutor(timeout_seconds=0.001, progress_opcodes=1).execute(database, sql)


def test_result_byte_cap(database: Path) -> None:
    with pytest.raises(ResultLimitError):
        ReadOnlySQLiteExecutor(max_bytes=10).execute(database, "SELECT * FROM values_table")


def test_executor_replaces_malformed_legacy_utf8(database: Path) -> None:
    result = ReadOnlySQLiteExecutor().execute(database, "SELECT CAST(x'80' AS TEXT)")
    assert result.rows == [["�"]]
