"""Construct the one local runtime path shared by CLI, API, UI, and evaluation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
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
from agentic_text2sql.layer2_grounding.semantic_catalog import load_semantic_catalog
from agentic_text2sql.layer2_grounding.service import GroundingService, IndexService
from agentic_text2sql.layer3_generation.easy_compiler import GroundedEasyCompiler
from agentic_text2sql.layer3_generation.generator import GeneratorAgent
from agentic_text2sql.layer3_generation.normalizer import CandidateNormalizer
from agentic_text2sql.layer3_generation.prompt_builder import (
    BASELINE_GENERATOR_PROMPT_VERSION,
    GENERATOR_PROMPT_VERSION,
    PromptBuilder,
)
from agentic_text2sql.layer3_generation.service import GenerationService
from agentic_text2sql.layer4_validation.executor import ReadOnlySQLiteExecutor
from agentic_text2sql.layer4_validation.policy import SQLSafetyPolicy
from agentic_text2sql.layer4_validation.service import ValidationService
from agentic_text2sql.layer5_correction.corrector import (
    BASELINE_CORRECTOR_PROMPT_VERSION,
    CORRECTOR_PROMPT_VERSION,
    CorrectorAgent,
)
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
        din_sql = settings.planning_mode == "din_sql"
        hybrid = settings.planning_mode == "hybrid"
        grounded_planning = din_sql or hybrid
        semantic_catalog_path = root / "datasets" / catalog.db_id / "semantic_catalog.yaml"
        semantic_catalog = (
            load_semantic_catalog(semantic_catalog_path, catalog)
            if grounded_planning and semantic_catalog_path.is_file()
            else None
        )
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
                "planner": (
                    "adaptive(planner_v2,planner_v3_din_sql)"
                    if hybrid
                    else "planner_v3_din_sql"
                    if din_sql
                    else "planner_v2"
                ),
                "generator": (
                    "adaptive(generator_v4_cross_domain,generator_v5_din_sql)"
                    if hybrid
                    else GENERATOR_PROMPT_VERSION
                    if din_sql
                    else BASELINE_GENERATOR_PROMPT_VERSION
                ),
                "corrector": (
                    "adaptive(corrector_v3_semantic_proof,corrector_v5_din_semantic_proof)"
                    if hybrid
                    else CORRECTOR_PROMPT_VERSION
                    if din_sql
                    else BASELINE_CORRECTOR_PROMPT_VERSION
                ),
            },
            "retrieval": {"mode": settings.retrieval_mode, "top_k": 20, "token_budget": 1200},
            "planning_mode": settings.planning_mode,
            "adaptive_policy": (
                {
                    "version": "adaptive_semantic_proof_first_v4",
                    "default_route": "BASELINE_PRESERVE",
                    "din_activation": "proven_semantic_binding_or_explicit_complex_dependency",
                    "fallback": "frozen_p6_planner_grounding_generation_correction",
                }
                if hybrid
                else None
            ),
            "semantic_catalog": (
                {
                    "version": semantic_catalog.version,
                    "sha256": hashlib.sha256(semantic_catalog_path.read_bytes()).hexdigest(),
                }
                if semantic_catalog is not None
                else None
            ),
            "correction": {
                "enabled": correction_enabled,
                "max_repairs": 2 if correction_enabled else 0,
                "max_llm_calls": 2 if correction_enabled else 0,
            },
        }
        self.embedding: OllamaEmbeddingClient | None = None
        generator_template = (
            "generator_v5_din_sql.j2" if din_sql else "generator_v4_cross_domain.j2"
        )
        corrector_template = (
            "corrector_v4_din_sql.j2" if din_sql else "corrector_v3_cross_domain.j2"
        )
        normalizer = CandidateNormalizer()
        policy = SQLSafetyPolicy(default_limit=200)
        executor = ReadOnlySQLiteExecutor(timeout_seconds=10, max_rows=200)
        grounding = None
        index_root = settings.resolved_data_dir / "indexes/p3_1_semantic"
        if (index_root / catalog.db_id / "active.json").is_file():
            pointer_path = index_root / catalog.db_id / "active.json"
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            embed_many: Callable[[list[str]], list[list[float]]]
            embed_query: Callable[[str], list[float]]
            if settings.retrieval_mode == "bm25":
                digest = str(model_config["embedding"]["digest"])
                embed_many = _disabled_embed_many
                embed_query = _disabled_embed_query
            else:
                self.embedding = OllamaEmbeddingClient(settings.ollama_base_url, "bge-m3:latest")
                digest = self.embedding.model_digest()
                embed_many = self._embed_many

                def active_embed_query(text: str) -> list[float]:
                    return self._embed_many([text])[0]

                embed_query = active_embed_query
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
                embed_many,
            )
            retriever = index_service.load(catalog.db_id, embed_query)
            grounding = GroundingService(
                retriever,
                catalog,
                mode=settings.retrieval_mode,
                top_k=20,
                token_budget=1200,
                semantic_catalog=semantic_catalog,
            )
        if grounded_planning and grounding is None:
            self.provider.close()
            raise RuntimeError("hybrid/DIN-SQL planning requires an active p3_1_semantic index")
        correction = None
        if correction_enabled:
            correction = CorrectionService(
                corrector=CorrectorAgent(
                    self.provider,
                    normalizer,
                    root / "configs/prompts" / corrector_template,
                    root / "datasets/olist/business_glossary.yaml",
                    settings.ollama_model,
                    (CORRECTOR_PROMPT_VERSION if din_sql else BASELINE_CORRECTOR_PROMPT_VERSION),
                ),
                validation=ValidationService(policy, executor),
                max_repairs=2,
                max_llm_calls=2,
            )
        din_correction = None
        if correction_enabled and hybrid:
            din_correction = CorrectionService(
                corrector=CorrectorAgent(
                    self.provider,
                    normalizer,
                    root / "configs/prompts/corrector_v4_din_sql.j2",
                    root / "datasets/olist/business_glossary.yaml",
                    settings.ollama_model,
                    CORRECTOR_PROMPT_VERSION,
                ),
                validation=ValidationService(policy, executor),
                max_repairs=2,
                max_llm_calls=2,
            )
        din_generation = None
        if hybrid:
            din_generation = GenerationService(
                PromptBuilder(
                    root / "configs/prompts/generator_v5_din_sql.j2",
                    root / "datasets/olist/business_glossary.yaml",
                ),
                GeneratorAgent(self.provider),
                normalizer,
                settings.ollama_model,
                GENERATOR_PROMPT_VERSION,
            )
        self.service = DirectBaselineService(
            router=QueryRouter(),
            decomposer=Decomposer(),
            planner=PlannerAgent(
                self.provider,
                root / "configs/prompts/planner_v2.j2",
                root / "configs/prompts/planner_v3_din_sql.j2",
            ),
            generation=GenerationService(
                PromptBuilder(
                    root / "configs/prompts" / generator_template,
                    root / "datasets/olist/business_glossary.yaml",
                ),
                GeneratorAgent(self.provider),
                normalizer,
                settings.ollama_model,
                GENERATOR_PROMPT_VERSION if din_sql else BASELINE_GENERATOR_PROMPT_VERSION,
            ),
            din_generation=din_generation,
            policy=policy,
            executor=executor,
            easy_compiler=GroundedEasyCompiler(normalizer),
            grounding=grounding,
            correction=correction,
            din_correction=din_correction,
            run_deadline_seconds=settings.run_deadline_seconds,
            planning_mode=settings.planning_mode,
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


def _disabled_embed_many(_: list[str]) -> list[list[float]]:
    raise RuntimeError("BM25 runtime must not invoke the embedding model")


def _disabled_embed_query(_: str) -> list[float]:
    raise RuntimeError("BM25 runtime must not invoke the embedding model")
