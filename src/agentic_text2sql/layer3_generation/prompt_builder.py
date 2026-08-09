"""Versioned direct-baseline prompt construction."""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.retrieval import SchemaContext
from agentic_text2sql.contracts.sql import SqlCandidate

GENERATOR_PROMPT_VERSION = "generator_v2_grounded"


def catalog_as_sqlite_context(catalog: CatalogSnapshot) -> str:
    lines = []
    for table in catalog.tables:
        columns = ", ".join(f"{column.name} {column.data_type}" for column in table.columns)
        lines.append(f"{table.kind.upper()} {table.name}({columns})")
        for foreign_key in table.foreign_keys:
            source = ", ".join(foreign_key.from_columns)
            target = ", ".join(foreign_key.target_columns)
            lines.append(f"FK {table.name}({source}) -> {foreign_key.target_table}({target})")
    return "\n".join(lines)


class PromptBuilder:
    def __init__(self, template_path: Path, glossary_path: Path) -> None:
        self.template_path = template_path
        self.glossary_path = glossary_path

    def build(
        self,
        question: str,
        plan: LogicalPlan,
        catalog: CatalogSnapshot,
        schema_context: SchemaContext | None = None,
    ) -> str:
        template = Environment(undefined=StrictUndefined, autoescape=False).from_string(
            self.template_path.read_text(encoding="utf-8")
        )
        return template.render(
            question=question,
            logical_plan=plan.model_dump_json(indent=2),
            schema_context=(
                schema_context.rendered_context
                if schema_context is not None
                else catalog_as_sqlite_context(catalog)
            ),
            schema_mode=(
                "Retrieved schema context with evidence"
                if schema_context is not None
                else "Full schema baseline"
            ),
            business_glossary=self.glossary_path.read_text(encoding="utf-8"),
            output_schema=json.dumps(SqlCandidate.model_json_schema(), ensure_ascii=False),
            catalog_hash=catalog.catalog_hash,
        )
