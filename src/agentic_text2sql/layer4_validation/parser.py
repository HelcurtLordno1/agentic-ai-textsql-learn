"""Single-statement SQLite parsing with stable failure messages."""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from agentic_text2sql.exceptions import Text2SQLError


class SQLParseError(Text2SQLError):
    """A SQL candidate could not be accepted as exactly one parsed statement."""


def parse_one(sql: str) -> exp.Expression:
    if not sql.strip():
        raise SQLParseError("SQL is empty")
    if "--" in sql or "/*" in sql or "*/" in sql:
        raise SQLParseError("SQL comments are not allowed")
    try:
        statements = [statement for statement in sqlglot.parse(sql, read="sqlite") if statement]
    except sqlglot.errors.ParseError as exc:
        raise SQLParseError("SQL syntax is invalid") from exc
    if len(statements) != 1:
        raise SQLParseError("Exactly one SQL statement is required")
    return statements[0]
