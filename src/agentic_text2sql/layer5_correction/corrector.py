"""Schema-grounded local corrector that returns a full normalized candidate."""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from agentic_text2sql.adapters.llm.base import StructuredLLM
from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.correction import AttemptSummary, CorrectionPlan
from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.retrieval import SchemaContext
from agentic_text2sql.contracts.sql import CandidateRecord, SqlCandidate
from agentic_text2sql.layer2_grounding.context_packer import estimate_tokens
from agentic_text2sql.layer3_generation.normalizer import CandidateNormalizer
from agentic_text2sql.layer3_generation.prompt_builder import (
    catalog_as_sqlite_context,
    domain_rules,
)

CORRECTOR_PROMPT_VERSION = "corrector_v4_schema_coherent"


class CorrectorAgent:
    def __init__(
        self,
        provider: StructuredLLM,
        normalizer: CandidateNormalizer,
        template_path: Path,
        glossary_path: Path,
        model_name: str,
    ) -> None:
        self.provider = provider
        self.normalizer = normalizer
        self.template_path = template_path
        self.glossary_path = glossary_path
        self.model_name = model_name

    def correct(
        self,
        *,
        question: str,
        plan: LogicalPlan,
        catalog: CatalogSnapshot,
        failed_candidate: CandidateRecord,
        correction_plan: CorrectionPlan,
        schema_context: SchemaContext | None,
        previous_attempts: list[AttemptSummary],
    ) -> CandidateRecord:
        template = Environment(undefined=StrictUndefined, autoescape=False).from_string(
            self.template_path.read_text(encoding="utf-8")
        )
        prompt = template.render(
            question=question,
            logical_plan=plan.model_dump_json(indent=2),
            schema_context=(
                schema_context.rendered_context
                if schema_context is not None
                else catalog_as_sqlite_context(catalog)
            ),
            business_glossary=domain_rules(catalog, self.glossary_path),
            failed_sql=failed_candidate.normalized_sql,
            correction_plan=correction_plan.model_dump_json(indent=2),
            previous_attempts=json.dumps(
                [item.model_dump(mode="json") for item in previous_attempts], ensure_ascii=False
            ),
            output_schema=json.dumps(SqlCandidate.model_json_schema(), ensure_ascii=False),
        )
        candidate = self.provider.generate_structured(prompt=prompt, response_model=SqlCandidate)
        return self.normalizer.normalize(
            candidate,
            model_name=self.model_name,
            prompt_version=CORRECTOR_PROMPT_VERSION,
            catalog_hash=catalog.catalog_hash,
            prompt_estimated_tokens=estimate_tokens(prompt),
        )
