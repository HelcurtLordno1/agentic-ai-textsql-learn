"""Layer 3 facade for prompt, one candidate, and normalization."""

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.retrieval import SchemaContext
from agentic_text2sql.contracts.sql import CandidateRecord
from agentic_text2sql.layer2_grounding.context_packer import estimate_tokens
from agentic_text2sql.layer3_generation.generator import GeneratorAgent
from agentic_text2sql.layer3_generation.normalizer import CandidateNormalizer
from agentic_text2sql.layer3_generation.prompt_builder import (
    GENERATOR_PROMPT_VERSION,
    PromptBuilder,
)


class GenerationService:
    def __init__(
        self,
        prompt_builder: PromptBuilder,
        generator: GeneratorAgent,
        normalizer: CandidateNormalizer,
        model_name: str,
    ) -> None:
        self.prompt_builder = prompt_builder
        self.generator = generator
        self.normalizer = normalizer
        self.model_name = model_name

    def run(
        self,
        question: str,
        plan: LogicalPlan,
        catalog: CatalogSnapshot,
        schema_context: SchemaContext | None = None,
    ) -> CandidateRecord:
        prompt = self.prompt_builder.build(question, plan, catalog, schema_context)
        candidate = self.generator.generate(prompt)
        return self.normalizer.normalize(
            candidate,
            model_name=self.model_name,
            prompt_version=GENERATOR_PROMPT_VERSION,
            catalog_hash=catalog.catalog_hash,
            prompt_estimated_tokens=estimate_tokens(prompt),
        )
