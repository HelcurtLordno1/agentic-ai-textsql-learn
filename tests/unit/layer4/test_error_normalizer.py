import sqlite3

import pytest

from agentic_text2sql.contracts.validation import ErrorClass
from agentic_text2sql.layer4_validation.error_normalizer import normalize_error


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (sqlite3.OperationalError("no such table: x"), ErrorClass.UNKNOWN_TABLE),
        (sqlite3.OperationalError("no such column: x"), ErrorClass.UNKNOWN_COLUMN),
        (sqlite3.OperationalError("ambiguous column name: x"), ErrorClass.AMBIGUOUS_COLUMN),
        (sqlite3.OperationalError("no such function: x"), ErrorClass.TYPE_OR_FUNCTION_ERROR),
        (sqlite3.OperationalError("near x: syntax error"), ErrorClass.SYNTAX_ERROR),
        (sqlite3.OperationalError("interrupted"), ErrorClass.TIMEOUT),
    ],
)
def test_error_taxonomy_is_stable(error: Exception, category: ErrorClass) -> None:
    report = normalize_error(error)
    assert report.error_class is category
    assert report.safe_message
    assert "traceback" not in report.safe_message.lower()
