"""Map parser/SQLite failures to a small sanitized operational taxonomy."""

from __future__ import annotations

import re
import sqlite3

from agentic_text2sql.contracts.validation import ErrorClass, ValidationReport


def normalize_error(error: BaseException) -> ValidationReport:
    message = str(error).lower()
    if "interrupted" in message or "timeout" in message:
        category = ErrorClass.TIMEOUT
        safe = "Query execution exceeded its deadline"
    elif "no such table" in message:
        category = ErrorClass.UNKNOWN_TABLE
        safe = "Query references an unknown table"
    elif "no such column" in message:
        category = ErrorClass.UNKNOWN_COLUMN
        safe = "Query references an unknown column"
    elif "ambiguous column" in message:
        category = ErrorClass.AMBIGUOUS_COLUMN
        safe = "Query contains an ambiguous column"
    elif "no such function" in message or "wrong number of arguments" in message:
        category = ErrorClass.TYPE_OR_FUNCTION_ERROR
        safe = "Query uses an unavailable function or invalid arguments"
    elif isinstance(error, sqlite3.OperationalError) and (
        "syntax" in message or "incomplete input" in message
    ):
        category = ErrorClass.SYNTAX_ERROR
        safe = "Query syntax is invalid"
    else:
        category = ErrorClass.UNKNOWN_RUNTIME_ERROR
        safe = "Query execution failed"
    safe = re.sub(r"(?:[a-zA-Z]:)?[/\\][^\s]+", "[path]", safe)
    return ValidationReport(accepted=False, error_class=category, safe_message=safe)
