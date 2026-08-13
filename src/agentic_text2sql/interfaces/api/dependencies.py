"""Application container and bounded local background executor."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import cast

from fastapi import Request

from agentic_text2sql.contracts.sql import DirectRunResult
from agentic_text2sql.layer6_application.catalog_registry import CatalogRegistry
from agentic_text2sql.layer6_application.feedback_store import SQLiteFeedbackStore
from agentic_text2sql.layer6_application.run_store import SQLiteRunStore
from agentic_text2sql.layer6_application.service import ApplicationQueryService
from agentic_text2sql.layer6_application.service_factory import runtime_bundle
from agentic_text2sql.settings import Settings


class ApplicationContainer:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        state_path = self.settings.resolved_artifact_dir / "application.sqlite"
        self.registry = CatalogRegistry(state_path)
        self.runs = SQLiteRunStore(state_path)
        self.recovered_run_ids = self.runs.recover_incomplete()
        self.feedback = SQLiteFeedbackStore(state_path)
        self.query_service = ApplicationQueryService(
            self.settings, self.registry, self.runs, runtime_bundle
        )
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="text2sql-query")
        self.futures: dict[str, Future[DirectRunResult]] = {}

    def dataset_path(self, dataset: str) -> tuple[str, Path]:
        if dataset == "olist":
            return "olist", self.settings.resolved_data_dir / "processed/olist.sqlite"
        if dataset == "synthetic_tiny":
            path = self.settings.project_root / "data/samples/synthetic_commerce_tiny.sqlite"
            return "synthetic_tiny", path
        raise KeyError(dataset)

    def submit(self, db_id: str, question: str, correction_enabled: bool) -> str:
        record = self.query_service.prepare(db_id, question, correction_enabled=correction_enabled)
        future = self.executor.submit(
            self.query_service.execute,
            record.run_id,
            correction_enabled=correction_enabled,
        )
        self.futures[record.run_id] = future
        future.add_done_callback(lambda completed: self._finish(record.run_id, completed))
        return record.run_id

    def _finish(self, run_id: str, future: Future[DirectRunResult]) -> None:
        # Observe exceptions (the service has already persisted FAILED) and bound memory use.
        if not future.cancelled():
            future.exception()
        self.futures.pop(run_id, None)

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)


def get_container(request: Request) -> ApplicationContainer:
    return cast(ApplicationContainer, request.app.state.container)
