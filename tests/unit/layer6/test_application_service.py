from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType
from typing import ClassVar

from agentic_text2sql.contracts.sql import DirectRunResult, DirectStatus
from agentic_text2sql.layer6_application.catalog_registry import CatalogRegistry
from agentic_text2sql.layer6_application.run_store import SQLiteRunStore
from agentic_text2sql.layer6_application.service import ApplicationQueryService
from agentic_text2sql.settings import Settings


class FakeRuntime:
    provenance: ClassVar[dict[str, object]] = {
        "generation_model_digest": "digest",
        "index_version": "version",
    }

    def __enter__(self) -> FakeRuntime:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback

    def run(self, question: str, database: Path, catalog: object) -> DirectRunResult:
        del database, catalog
        return DirectRunResult(
            run_id="runtime-id",
            question=question,
            status=DirectStatus.SUCCEEDED,
            route_reason="query",
            prompt_versions={"planner": "v1", "generator": "v2"},
            result_columns=["count"],
            result_rows=[[2]],
            latency_ms={
                "route": 1,
                "planning": 2,
                "grounding": 3,
                "generation": 4,
                "validation": 5,
                "correction": 0,
                "total": 15,
            },
        )


def database(tmp_path: Path) -> Path:
    path = tmp_path / "tiny.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE orders(id INTEGER PRIMARY KEY)")
    return path


def test_application_persists_complete_six_layer_story(tmp_path: Path) -> None:
    settings = Settings(PROJECT_ROOT=tmp_path, TEXT2SQL_ARTIFACT_DIR=tmp_path / "artifacts")
    state = tmp_path / "application.sqlite"
    registry = CatalogRegistry(state)
    registry.register("tiny", database(tmp_path))
    runs = SQLiteRunStore(state)
    service = ApplicationQueryService(
        settings,
        registry,
        runs,
        lambda *args, **kwargs: FakeRuntime(),
    )

    record = service.run("tiny", "Count orders")

    assert record.status.value == "COMPLETED"
    assert record.result is not None
    assert record.result["run_id"] == record.run_id
    assert record.config["generation_model_digest"] == "digest"
    assert record.config["index_version"] == "version"
    layers = [event.layer for event in runs.events(record.run_id)]
    assert layers == ["0", "1", "2", "3", "4", "5", "6"]
    assert runs.events(record.run_id)[5].details["state"] == "SKIPPED"
