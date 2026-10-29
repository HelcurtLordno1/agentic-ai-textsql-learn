"""Bounded catalog facts for a failed column reference, without guessed joins."""

from __future__ import annotations

import re

from agentic_text2sql.contracts.catalog import CatalogSnapshot


def column_owner_feedback(message: str | None, catalog: CatalogSnapshot) -> dict[str, object]:
    match = re.fullmatch(r"Unknown column: ([\w.]+)", message or "")
    if match is None:
        return {}
    reference = match.group(1)
    name = reference.rsplit(".", 1)[-1]
    owners = [table for table in catalog.tables if any(c.name == name for c in table.columns)]
    if not owners or len(owners) > 4:
        return {}  # Ambiguous/wide catalog facts must not overflow the repair budget.
    owner_names = {table.name for table in owners}
    relations = []
    for table in owners:
        key_columns = [column.name for column in table.columns if column.primary_key_position]
        foreign_columns = [column for fk in table.foreign_keys for column in fk.from_columns]
        relevant = list(dict.fromkeys([name, *key_columns, *foreign_columns]))[:12]
        relations.append({"relation": table.name, "kind": table.kind, "columns": relevant})
    edges = []
    for table in catalog.tables:
        for fk in table.foreign_keys:
            if table.name in owner_names or fk.target_table in owner_names:
                edges.append(
                    {
                        "source": table.name,
                        "columns": fk.from_columns,
                        "target": fk.target_table,
                        "target_columns": fk.target_columns,
                    }
                )
    return {
        "failed_reference": reference,
        "existing_owners": relations,
        "declared_foreign_keys": edges[:8],
        "scope": "Catalog alternatives only; choose by question semantics, never by name alone",
    }
