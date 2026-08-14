"""Construct the one local runtime path shared by CLI, API, UI, and evaluation."""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType

import yaml

from agentic_text2sql.adapters.embeddings.ollama_embeddings import OllamaEmbeddingClient
from agentic_text2sql.adapters.llm.ollama_provider import OllamaProvider
from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.sql import DirectRunResult
from agentic_text2sql.layer1_reasoning.decomposer import Decomposer
from agentic_text2sql.layer1_reasoning.planner import PlannerAgent
from agentic_text2sql.layer1_reasoning.router import QueryRouter
from agentic_text2sql.layer2_grounding.service import GroundingService, IndexService
from agentic_text2sql.layer3_generation.generator import GeneratorAgent
from agentic_text2sql.layer3_generation.normalizer import CandidateNormalizer
from agentic_text2sql.layer3_generation.prompt_builder import PromptBuilder
from agentic_text2sql.layer3_generation.service import GenerationService
from agentic_text2sql.layer4_validation.executor import ReadOnlySQLiteExecutor
from agentic_text2sql.layer4_validation.policy import SQLSafetyPolicy
from agentic_text2sql.layer4_validation.service import ValidationService
from agentic_text2sql.layer5_correction.corrector import CorrectorAgent
from agentic_text2sql.layer5_correction.service import CorrectionService
from agentic_text2sql.layer6_application.query_service import DirectBaselineService
from agentic_text2sql.settings import Settings


class RuntimeBundle(AbstractContextManager["RuntimeBundle"]):
    def __init__(
        self,
        settings: Settings,
        catalog: CatalogSnapshot,
        *,
        correction_enabled: bool,
    ) -> None:
        root = settings.project_root
        self.provider = OllamaProvider(settings)
        generation_digest = next(
            (
                str(item["digest"])
                for item in self.provider.list_models()
                if item.get("name") == settings.ollama_model and isinstance(item.get("digest"), str)
            ),
            "unknown",
        )
        model_config = yaml.safe_load((root / "configs/models.yaml").read_text(encoding="utf-8"))
        expected_generation_digest = str(model_config["generator"]["digest"])
        if generation_digest != expected_generation_digest:
            self.provider.close()
            raise RuntimeError(
                "generation model digest mismatch: "
                f"expected {expected_generation_digest}, got {generation_digest}"
            )
        self.provenance: dict[str, object] = {
            "generation_model": settings.ollama_model,
            "generation_model_digest": generation_digest,
            "ollama_options": {
                "temperature": 0,
                "num_ctx": 4096,
                "num_gpu": settings.ollama_num_gpu,
                "seed": settings.ollama_seed,
            },
            "prompt_versions": {
                "planner": "planner_v2",
                "generator": "generator_v4_cross_domain",
                "corrector": "corrector_v3_cross_domain",
            },
            "retrieval": {"mode": "hybrid", "top_k": 20, "token_budget": 1200},
            "correction": {
                "enabled": correction_enabled,
                "max_repairs": 1 if correction_enabled else 0,
                "max_llm_calls": 1 if correction_enabled else 0,
            },
        }
        self.embedding: OllamaEmbeddingClient | None = None
        normalizer = CandidateNormalizer()
        policy = SQLSafetyPolicy(default_limit=200)
        executor = ReadOnlySQLiteExecutor(timeout_seconds=10, max_rows=200)
        grounding = None
        index_root = settings.resolved_data_dir / "indexes/p3_1_semantic"
        if (index_root / catalog.db_id / "active.json").is_file():
            pointer = json.loads(
                (index_root / catalog.db_id / "active.json").read_text(encoding="utf-8")
            )
            self.embedding = OllamaEmbeddingClient(settings.ollama_base_url, "bge-m3:latest")
            digest = self.embedding.model_digest()
            self.provenance.update(
                {
                    "embedding_model_digest": digest,
                    "index_version": pointer["version_id"],
                    "catalog_hash": catalog.catalog_hash,
                }
            )
            index_service = IndexService(
                index_root,
                "bge-m3:latest",
                digest,
                lambda texts: self._embed_many(texts),
            )
            retriever = index_service.load(catalog.db_id, lambda text: self._embed_many([text])[0])
            grounding = GroundingService(
                retriever, catalog, mode="hybrid", top_k=20, token_budget=1200
            )
        correction = None
        if correction_enabled:
            correction = CorrectionService(
                corrector=CorrectorAgent(
                    self.provider,
                    normalizer,
                    root / "configs/prompts/corrector_v3_cross_domain.j2",
                    root / "datasets/olist/business_glossary.yaml",
                    settings.ollama_model,
                ),
                validation=ValidationService(policy, executor),
                max_repairs=1,
                max_llm_calls=1,
            )
        self.service = DirectBaselineService(
            router=QueryRouter(),
            decomposer=Decomposer(),
            planner=PlannerAgent(self.provider, root / "configs/prompts/planner_v2.j2"),
            generation=GenerationService(
                PromptBuilder(
                    root / "configs/prompts/generator_v4_cross_domain.j2",
                    root / "datasets/olist/business_glossary.yaml",
                ),
                GeneratorAgent(self.provider),
                normalizer,
                settings.ollama_model,
            ),
            policy=policy,
            executor=executor,
            grounding=grounding,
            correction=correction,
            run_deadline_seconds=settings.run_deadline_seconds,
        )

    def _embed_many(self, texts: list[str]) -> list[list[float]]:
        if self.embedding is None:
            raise RuntimeError("Embedding client is not configured")
        return self.embedding.embed(texts, batch_size=32)

    def run(self, question: str, database: Path, catalog: CatalogSnapshot) -> DirectRunResult:
        provider_before = self.provider.telemetry.milliseconds()
        embedding_before = dict(self.embedding.telemetry) if self.embedding is not None else {}
        result = self.service.run(question, database, catalog)
        telemetry = {
            key: value - provider_before.get(key, 0)
            for key, value in self.provider.telemetry.milliseconds().items()
        }
        if self.embedding is not None:
            telemetry.update(
                {
                    key: value - embedding_before.get(key, 0)
                    for key, value in self.embedding.telemetry.items()
                }
            )
        return result.model_copy(update={"latency_ms": {**result.latency_ms, **telemetry}})

    def __enter__(self) -> RuntimeBundle:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.provider.close()
        if self.embedding is not None:
            self.embedding.close()


def runtime_bundle(
    settings: Settings, catalog: CatalogSnapshot, correction_enabled: bool
) -> RuntimeBundle:
    return RuntimeBundle(settings, catalog, correction_enabled=correction_enabled)
