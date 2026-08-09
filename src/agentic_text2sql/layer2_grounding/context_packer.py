"""Final schema-context rendering and conservative token estimation."""

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.retrieval import RankedDocument


def estimate_tokens(text: str) -> int:
    # UTF-8 bytes / 3 is deliberately conservative for mixed Vietnamese/English SQL identifiers.
    return max(1, (len(text.encode("utf-8")) + 2) // 3)


def render_schema_context(
    catalog: CatalogSnapshot,
    selected_tables: set[str],
    selected_columns: set[str],
    joins: list[str],
) -> str:
    lines: list[str] = []
    for table in catalog.tables:
        if table.name not in selected_tables:
            continue
        qualified = {value for value in selected_columns if value.startswith(f"{table.name}.")}
        columns = [
            column
            for column in table.columns
            if f"{table.name}.{column.name}" in qualified or column.primary_key_position > 0
        ]
        if not columns and table.columns:
            columns = [table.columns[0]]
        rendered = ", ".join(f"{column.name} {column.data_type}" for column in columns)
        lines.append(f"{table.kind.upper()} {table.name}({rendered})")
    lines.extend(f"FK {join}" for join in joins)
    return "\n".join(lines)


def pack_candidates(
    candidates: list[RankedDocument], token_budget: int
) -> tuple[tuple[RankedDocument, ...], int]:
    if token_budget < 1:
        raise ValueError("token_budget must be positive")
    packed: list[RankedDocument] = []
    used = 0
    for candidate in candidates:
        cost = estimate_tokens(candidate.document.retrieval_text())
        if used + cost <= token_budget:
            packed.append(candidate)
            used += cost
    return tuple(packed), used
