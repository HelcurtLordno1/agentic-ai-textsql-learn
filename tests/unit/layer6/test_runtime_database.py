import sqlite3
from pathlib import Path

from agentic_text2sql.layer6_application.runtime_database import stage_runtime_database


def test_runtime_database_is_atomic_readonly_and_reused(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE sample(value INTEGER)")
        connection.execute("INSERT INTO sample VALUES (42)")

    cache = tmp_path / "runtime"
    first = stage_runtime_database(source, cache, "sample")
    second = stage_runtime_database(source, cache, "sample")

    assert first == second
    assert first.parent == cache
    assert first.stat().st_mode & 0o222 == 0
    with sqlite3.connect(f"file:{first}?mode=ro", uri=True) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == (42,)


def test_runtime_database_identity_changes_with_source(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE sample(value INTEGER)")
    first = stage_runtime_database(source, tmp_path / "runtime", "sample")

    with sqlite3.connect(source) as connection:
        connection.execute("INSERT INTO sample VALUES (1)")
    second = stage_runtime_database(source, tmp_path / "runtime", "sample")

    assert first != second
