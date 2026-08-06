from pathlib import Path

import pytest

from agentic_text2sql.contracts.validation import ErrorClass
from agentic_text2sql.layer2_grounding.introspector import SQLiteIntrospector
from agentic_text2sql.layer4_validation.policy import SQLSafetyPolicy


@pytest.fixture
def catalog():
    database = Path(__file__).resolve().parents[3] / "data/samples/synthetic_commerce_tiny.sqlite"
    return SQLiteIntrospector().inspect(database, "synthetic")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT customer_id FROM customers",
        "WITH delivered AS (SELECT * FROM orders WHERE status = 'delivered') "
        "SELECT * FROM delivered",
        "SELECT COUNT(*) FROM orders",
        "SELECT customer_id FROM customers UNION SELECT customer_id FROM orders",
    ],
)
def test_allows_read_queries(sql: str, catalog) -> None:
    decision = SQLSafetyPolicy(default_limit=25).evaluate(sql, catalog)
    assert decision.allowed
    assert decision.normalized_sql is not None


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO customers VALUES ('evil', 'x', 'VN')",
        "UPDATE customers SET name = 'evil'",
        "DELETE FROM customers",
        "DROP TABLE customers",
        "CREATE TABLE evil(x)",
        "ATTACH DATABASE '/tmp/evil.db' AS evil",
        "PRAGMA user_version",
        "SELECT * FROM customers; DELETE FROM customers",
        "SELECT load_extension('evil')",
        "SELECT * FROM sqlite_master",
        "SELECT 1 /* hidden */; DROP TABLE customers",
    ],
)
def test_blocks_unsafe_queries(sql: str, catalog) -> None:
    decision = SQLSafetyPolicy().evaluate(sql, catalog)
    assert not decision.allowed
    assert decision.error_class in {ErrorClass.POLICY_VIOLATION, ErrorClass.SYNTAX_ERROR}


def test_blocks_unknown_schema(catalog) -> None:
    table = SQLSafetyPolicy().evaluate("SELECT * FROM invented", catalog)
    column = SQLSafetyPolicy().evaluate("SELECT invented FROM customers", catalog)
    assert table.error_class is ErrorClass.UNKNOWN_TABLE
    assert column.error_class is ErrorClass.UNKNOWN_COLUMN


def test_injects_limit_only_for_non_scalar_query(catalog) -> None:
    rows = SQLSafetyPolicy(default_limit=17).evaluate("SELECT * FROM customers", catalog)
    scalar = SQLSafetyPolicy(default_limit=17).evaluate("SELECT COUNT(*) FROM customers", catalog)
    assert rows.limit_injected and "LIMIT 17" in (rows.normalized_sql or "")
    assert not scalar.limit_injected and "LIMIT" not in (scalar.normalized_sql or "")
