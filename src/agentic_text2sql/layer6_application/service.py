"""Persistent Layer 6 orchestration around the verified runtime."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.sql import DirectRunResult
from agentic_text2sql.contracts.trace import RunRecord, RunStatus, TraceEvent
from agentic_text2sql.layer6_application.catalog_registry import CatalogRegistry
from agentic_text2sql.layer6_application.run_store import SQLiteRunStore
from agentic_text2sql.settings import Settings


class QueryRuntime(Protocol):
    def run(self, question: str, database: Path, catalog: CatalogSnapshot) -> DirectRunResult: ...


RuntimeFactory = Callable[..., AbstractContextManager[QueryRuntime]]


class ApplicationQueryService:
    def __init__(
        self,
        settings: Settings,
        registry: CatalogRegistry,
        runs: SQLiteRunStore,
        runtime_factory: RuntimeFactory,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.runs = runs
        self.runtime_factory = runtime_factory

    def prepare(
        self,
        db_id: str,
        question: str,
        run_id: str | None = None,
        *,
        correction_enabled: bool = False,
    ) -> RunRecord:
        normalized = " ".join(question.split())
        if not 1 <= len(normalized) <= 2000:
            raise ValueError("question must contain between 1 and 2000 characters")
        self.registry.resolve(db_id)
        return self.runs.create(
            run_id or str(uuid.uuid4()),
            db_id,
            normalized,
            {
                "generation_model": self.settings.ollama_model,
                "ollama_num_gpu": self.settings.ollama_num_gpu,
                "embedding_model": "bge-m3:latest",
                "correction_enabled": correction_enabled,
                "max_repairs": 1,
                "max_correction_llm_calls": 1,
                "executor_timeout_seconds": 10,
                "max_result_rows": 200,
                "run_deadline_seconds": 60,
            },
        )

    def execute(self, run_id: str, *, correction_enabled: bool = False) -> DirectRunResult:
        record = self.runs.get(run_id)
        database, catalog = self.registry.resolve(record.db_id)
        self.runs.set_status(run_id, RunStatus.RUNNING)
        self.runs.append_event(
            TraceEvent(run_id=run_id, layer="0", event="RUN_STARTED", elapsed_ms=0)
        )
        try:
            with self.runtime_factory(
                self.settings, catalog, correction_enabled=correction_enabled
            ) as runtime:
                provenance = getattr(runtime, "provenance", None)
                if isinstance(provenance, dict):
                    self.runs.update_config(run_id, provenance)
                result = runtime.run(record.question, database, catalog)
        except Exception as exc:
            self.runs.append_event(
                TraceEvent(
                    run_id=run_id,
                    layer="6",
                    event="FAILED",
                    elapsed_ms=0,
                    details={"error": type(exc).__name__},
                )
            )
            self.runs.set_status(run_id, RunStatus.FAILED)
            raise
        result = result.model_copy(update={"run_id": run_id})
        self._persist_layer_events(run_id, result)
        self.runs.set_status(run_id, RunStatus.COMPLETED, result.model_dump(mode="json"))
        return result

    def run(self, db_id: str, question: str, *, correction_enabled: bool = False) -> RunRecord:
        prepared = self.prepare(db_id, question, correction_enabled=correction_enabled)
        self.execute(prepared.run_id, correction_enabled=correction_enabled)
        return self.runs.get(prepared.run_id)

    def _persist_layer_events(self, run_id: str, result: DirectRunResult) -> None:
        mappings = (
            ("1", "PLANNED", ("route", "planning")),
            ("2", "GROUNDED", ("grounding",)),
            ("3", "GENERATED", ("generation",)),
            ("4", "VALIDATED", ("policy", "execution", "validation")),
            ("5", "CORRECTED", ("correction",)),
        )
        for layer, event, keys in mappings:
            elapsed = sum(result.latency_ms.get(key, 0.0) for key in keys)
            details = {"status": result.status.value}
            if layer == "5":
                details["state"] = "USED" if result.correction else "SKIPPED"
            elif elapsed == 0:
                details["state"] = "SKIPPED"
            else:
                details["state"] = "COMPLETED"
            self.runs.append_event(
                TraceEvent(
                    run_id=run_id,
                    layer=layer,
                    event=event,
                    elapsed_ms=elapsed,
                    details=details,
                )
            )
        self.runs.append_event(
            TraceEvent(
                run_id=run_id,
                layer="6",
                event="PRESENTED",
                elapsed_ms=result.latency_ms.get("total", 0),
                details={"final_status": result.status.value},
            )
        )
