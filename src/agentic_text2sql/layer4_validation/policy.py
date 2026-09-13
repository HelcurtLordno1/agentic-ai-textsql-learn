"""AST-based read-only SQLite policy independent from model prompts."""

from __future__ import annotations

from sqlglot import exp
from sqlglot.optimizer.scope import Scope, traverse_scope

from agentic_text2sql.contracts.catalog import CatalogSnapshot, TableInfo
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


def _scope_output_columns(
    scope: Scope,
    allowed_tables: dict[str, TableInfo],
    cache: dict[int, set[str]],
) -> set[str]:
    """Resolve names exported by one CTE/derived-table scope without trusting SQL text."""
    key = id(scope)
    if key in cache:
        return cache[key]
    outputs = {
        selection.alias_or_name
        for selection in scope.expression.selects
        if selection.alias_or_name and not selection.is_star
    }
    if any(selection.is_star for selection in scope.expression.selects):
        for source in scope.sources.values():
            if isinstance(source, Scope):
                outputs.update(_scope_output_columns(source, allowed_tables, cache))
            elif isinstance(source, exp.Table) and source.name in allowed_tables:
                table = allowed_tables[source.name]
                outputs.update(column.name for column in table.columns)
    cache[key] = outputs
    return outputs


def _source_columns(
    scope: Scope,
    allowed_tables: dict[str, TableInfo],
    cache: dict[int, set[str]],
) -> dict[str, set[str]]:
    columns: dict[str, set[str]] = {}
    for alias, source in scope.sources.items():
        if isinstance(source, Scope):
            columns[alias] = _scope_output_columns(source, allowed_tables, cache)
        elif isinstance(source, exp.Table) and source.name in allowed_tables:
            table = allowed_tables[source.name]
            columns[alias] = {column.name for column in table.columns}
    return columns


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

        scope_output_cache: dict[int, set[str]] = {}
        for scope in traverse_scope(statement):
            source_columns = _source_columns(scope, allowed_tables, scope_output_cache)
            projection_aliases = {
                item.alias for item in scope.expression.selects if getattr(item, "alias", "")
            }
            external_columns = set(scope.external_columns)
            for column in scope.columns:
                if column.is_star:
                    continue
                qualifier = column.table
                if qualifier:
                    if qualifier in source_columns:
                        if column.name not in source_columns[qualifier]:
                            return _blocked(
                                f"Unknown column: {qualifier}.{column.name}",
                                ErrorClass.UNKNOWN_COLUMN,
                            )
                        continue
                    table_name = aliases.get(qualifier, qualifier)
                    table_info = allowed_tables.get(table_name)
                    if table_info is not None and column.name not in {
                        item.name for item in table_info.columns
                    }:
                        return _blocked(
                            f"Unknown column: {qualifier}.{column.name}",
                            ErrorClass.UNKNOWN_COLUMN,
                        )
                    continue
                if column.name in projection_aliases or any(
                    column.name in names for names in source_columns.values()
                ):
                    continue
                # sqlglot marks correlated references as external to the child scope. Resolve
                # these against catalog columns visible to an outer scope, preserving support for
                # safe correlated subqueries without letting an invented local name through.
                if column in external_columns and any(
                    column.name in {item.name for item in table.columns}
                    for table in allowed_tables.values()
                ):
                    continue
                return _blocked(f"Unknown column: {column.name}", ErrorClass.UNKNOWN_COLUMN)

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
