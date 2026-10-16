"""Construct the one local runtime path shared by CLI, API, UI, and evaluation."""

from __future__ import annotations

import json
import time
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
from agentic_text2sql.layer6_application.a1_service import A1QueryService
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
        setup_started = time.monotonic()
        self.provider = OllamaProvider(settings)
        self.embedding: OllamaEmbeddingClient | None = None
        try:
            self._configure(settings, catalog, correction_enabled)
        except BaseException:
            self.provider.close()
            if self.embedding is not None:
                self.embedding.close()
            raise
        self.setup_ms = (time.monotonic() - setup_started) * 1000

    def _configure(
        self, settings: Settings, catalog: CatalogSnapshot, correction_enabled: bool
    ) -> None:
        root = settings.project_root
        generation_digest = next(
            (
                str(item["digest"])
                for item in self.provider.list_models()
                if item.get("name") == settings.ollama_model and isinstance(item.get("digest"), str)
            ),
            "unknown",
        )
        model_config = yaml.safe_load((root / "configs/models.yaml").read_text(encoding="utf-8"))
        expected_generation_digest = (
            settings.generation_model_digest
            if settings.pipeline_mode == "a1" and settings.generation_model_digest is not None
            else str(model_config["generator"]["digest"])
        )
        if generation_digest != expected_generation_digest:
            raise RuntimeError(
                "generation model digest mismatch: "
                f"expected {expected_generation_digest}, got {generation_digest}"
            )
        self.provenance: dict[str, object] = {
            "pipeline_mode": settings.pipeline_mode,
            "critic_mode": settings.critic_mode,
            "generation_format": settings.generation_format,
            "generation_model": settings.ollama_model,
            "generation_model_digest": generation_digest,
            "ollama_options": {
                "temperature": 0,
                "num_ctx": 4096,
                "num_gpu": settings.ollama_num_gpu,
                "num_thread": settings.ollama_num_thread,
                "num_batch": settings.ollama_num_batch,
                "num_predict": settings.output_token_budget,
                "keep_alive": 0,
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
        self.provenance.update(
            {
                "ollama_version": self.provider.version(),
                "generation_template": self.provider.model_metadata(settings.ollama_model),
            }
        )
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
            if retriever.catalog_hash != catalog.catalog_hash:
                raise ValueError(
                    "Active index is stale for this catalog; rebuild it before inference"
                )
            grounding = GroundingService(
                retriever, catalog, mode="hybrid", top_k=20, token_budget=1200
            )
        if grounding is None:
            self.provenance["retrieval"] = {
                "mode": "full_catalog",
                "catalog_hash": catalog.catalog_hash,
            }
        correction = None
        self.service: DirectBaselineService | A1QueryService
        if settings.pipeline_mode == "a1":
            self.provenance.update(
                {
                    "prompt_versions": {
                        "generator": "a1-question-evidence-v1",
                        "critic": "a1-critic-v2",
                        "corrector": "a1-repair-v2",
                    },
                    "max_generation_requests": settings.a1_max_requests,
                    "input_token_budget": settings.input_token_budget,
                    "output_token_budget": settings.output_token_budget,
                    "semantic_repair_enabled": correction_enabled
                    and settings.critic_mode == "repair",
                    "operational_repair_enabled": correction_enabled
                    and settings.critic_mode == "repair",
                    "critic_shadow_sample_rate": settings.critic_shadow_sample_rate,
                    "repair_feedback_mode": settings.repair_feedback_mode,
                    "compute_policy": settings.compute_policy,
                    "deterministic_repair": settings.deterministic_repair,
                    "repairability_routing": settings.repairability_routing,
                    "trace_version": "a1-trace-v3",
                }
            )
            self.service = A1QueryService(
                self.provider, settings, grounding=grounding, correction_enabled=correction_enabled
            )
            return
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
        return result.model_copy(
            update={
                "latency_ms": {
                    **result.latency_ms,
                    **telemetry,
                    "runtime_setup": self.setup_ms,
                    "runtime_end_to_end": self.setup_ms + result.latency_ms.get("total", 0),
                }
            }
        )

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
