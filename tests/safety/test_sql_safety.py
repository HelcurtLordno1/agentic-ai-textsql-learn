import hashlib
from pathlib import Path

import pytest

from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer4_validation.executor import ReadOnlySQLiteExecutor
from agentic_text2sql.layer4_validation.policy import SQLSafetyPolicy

ROOT = Path(__file__).resolve().parents[2]
DATABASE = ROOT / "data/samples/synthetic_commerce_tiny.sqlite"
MALICIOUS = [
    "INSERT INTO customers VALUES ('x', 'x', 'VN')",
    "UPDATE customers SET name='x'",
    "DELETE FROM customers",
    "DROP TABLE customers",
    "ALTER TABLE customers ADD COLUMN evil TEXT",
    "CREATE TABLE evil(x)",
    "ATTACH DATABASE '/tmp/evil.sqlite' AS evil",
    "DETACH DATABASE main",
    "PRAGMA writable_schema=ON",
    "SELECT 1; DELETE FROM customers",
    "SELECT load_extension('evil')",
    "SELECT * FROM sqlite_schema",
    "SELECT * FROM customers -- obfuscated",
]


def checksum() -> str:
    return hashlib.sha256(DATABASE.read_bytes()).hexdigest()


@pytest.mark.parametrize("sql", MALICIOUS)
def test_every_malicious_fixture_is_blocked_and_database_unchanged(sql: str) -> None:
    before = checksum()
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")
    decision = SQLSafetyPolicy().evaluate(sql, catalog)
    assert not decision.allowed
    assert checksum() == before


def test_safe_fixture_executes_and_database_remains_unchanged() -> None:
    before = checksum()
    catalog = SQLiteIntrospector().inspect(DATABASE, "synthetic")
    decision = SQLSafetyPolicy().evaluate("SELECT COUNT(*) FROM orders", catalog)
    assert decision.allowed and decision.normalized_sql
    result = ReadOnlySQLiteExecutor().execute(DATABASE, decision.normalized_sql)
    assert result.rows == [[4]]
    assert checksum() == before
