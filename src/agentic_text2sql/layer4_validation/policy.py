"""AST-based read-only SQLite policy independent from model prompts."""

from __future__ import annotations

from sqlglot import exp
from sqlglot.optimizer.scope import Scope, traverse_scope

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.validation import ErrorClass, PolicyDecision
from agentic_text2sql.layer4_validation.parser import SQLParseError, parse_one

UNSAFE_FUNCTIONS = {"load_extension", "readfile", "writefile", "fts3_tokenizer"}
FORBIDDEN_NODE_NAMES = {
    "Insert",
    "Update",
    "Delete",
    "Merge",
    "Drop",
    "Alter",
    "Create",
    "Attach",
    "Detach",
    "Pragma",
    "Command",
    "Transaction",
    "Commit",
    "Rollback",
}


def _blocked(message: str, error: ErrorClass = ErrorClass.POLICY_VIOLATION) -> PolicyDecision:
    return PolicyDecision(allowed=False, error_class=error, safe_message=message)


class SQLSafetyPolicy:
    def __init__(self, *, default_limit: int = 200) -> None:
        self.default_limit = default_limit

    def evaluate(self, sql: str, catalog: CatalogSnapshot) -> PolicyDecision:
        try:
            statement = parse_one(sql)
        except SQLParseError as exc:
            return _blocked(str(exc), ErrorClass.SYNTAX_ERROR)
        if not isinstance(statement, exp.Query):
            return _blocked("Only read queries are allowed")
        for node in statement.walk():
            if type(node).__name__ in FORBIDDEN_NODE_NAMES:
                return _blocked(f"Operation {type(node).__name__.upper()} is not allowed")
        for function in statement.find_all(exp.Func):
            name = str(function.name).lower()
            if name in UNSAFE_FUNCTIONS:
                return _blocked(f"Function {name} is not allowed")

        allowed_tables = {table.name: table for table in catalog.tables}
        cte_names = {cte.alias_or_name for cte in statement.find_all(exp.CTE)}
        aliases: dict[str, str] = {}
        referenced_tables: set[str] = set()
        for table_expression in statement.find_all(exp.Table):
            name = table_expression.name
            if name in cte_names:
                continue
            if name.lower().startswith("sqlite_"):
                return _blocked("SQLite internal tables are not allowed")
            if name not in allowed_tables:
                return _blocked(f"Unknown table: {name}", ErrorClass.UNKNOWN_TABLE)
            referenced_tables.add(name)
            aliases[table_expression.alias_or_name] = name

        for column in statement.find_all(exp.Column):
            if column.is_star:
                continue
            qualifier = column.table
            if qualifier:
                table_name = aliases.get(qualifier, qualifier)
                if table_name in cte_names:
                    continue
                table_info = allowed_tables.get(table_name)
                if table_info is None:
                    continue
                if column.name not in {item.name for item in table_info.columns}:
                    return _blocked(
                        f"Unknown column: {qualifier}.{column.name}", ErrorClass.UNKNOWN_COLUMN
                    )
            elif referenced_tables and not any(
                column.name in {item.name for item in allowed_tables[name].columns}
                for name in referenced_tables
            ):
                # Projection aliases are valid in ORDER BY/GROUP BY and are not catalog columns.
                projection_aliases = {
                    item.alias for item in statement.selects if getattr(item, "alias", "")
                }
                if column.name not in projection_aliases:
                    return _blocked(f"Unknown column: {column.name}", ErrorClass.UNKNOWN_COLUMN)

        # Fail closed on implicit correlated references. An unqualified column must resolve inside
        # its own SELECT scope; outer-scope references remain supported when explicitly qualified.
        for scope in traverse_scope(statement):
            local_columns: set[str] = set()
            for source in scope.sources.values():
                if isinstance(source, exp.Table) and source.name in allowed_tables:
                    local_columns.update(
                        column.name for column in allowed_tables[source.name].columns
                    )
                elif isinstance(source, Scope):
                    local_columns.update(source.expression.named_selects)
            if not local_columns or not isinstance(scope.expression, exp.Select):
                continue
            projection_aliases = {
                item.alias for item in scope.expression.selects if getattr(item, "alias", "")
            }
            for column in scope.columns:
                if column.table or column.name in projection_aliases:
                    continue
                if column.find_ancestor(exp.Select) is not scope.expression:
                    continue
                if column.name not in local_columns:
                    return _blocked(
                        f"Unknown column in local query scope: {column.name}",
                        ErrorClass.UNKNOWN_COLUMN,
                    )

        limit_injected = False
        scalar_aggregate = (
            isinstance(statement, exp.Select)
            and statement.find(exp.AggFunc) is not None
            and statement.args.get("group") is None
        )
        if statement.args.get("limit") is None and not scalar_aggregate:
            statement = statement.limit(self.default_limit, copy=True)
            limit_injected = True
        return PolicyDecision(
            allowed=True,
            normalized_sql=statement.sql(dialect="sqlite"),
            limit_injected=limit_injected,
        )
