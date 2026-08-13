from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType

from fastapi.testclient import TestClient

from agentic_text2sql.contracts.sql import DirectRunResult, DirectStatus
from agentic_text2sql.interfaces.api.app import create_app
from agentic_text2sql.interfaces.api.dependencies import ApplicationContainer
from agentic_text2sql.settings import Settings


class FakeRuntime:
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
            run_id="runtime",
            question=question,
            status=DirectStatus.SUCCEEDED,
            route_reason="query",
            prompt_versions={},
            result_columns=["answer"],
            result_rows=[[42]],
            latency_ms={"route": 1, "planning": 1, "generation": 1, "execution": 1, "total": 4},
        )


def make_container(tmp_path: Path) -> ApplicationContainer:
    data = tmp_path / "data"
    (data / "processed").mkdir(parents=True)
    database = data / "processed/olist.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE orders(id INTEGER PRIMARY KEY)")
    settings = Settings(
        PROJECT_ROOT=tmp_path,
        TEXT2SQL_DATA_DIR=data,
        TEXT2SQL_ARTIFACT_DIR=tmp_path / "artifacts",
    )
    container = ApplicationContainer(settings)
    container.query_service.runtime_factory = lambda *args, **kwargs: FakeRuntime()
    return container


def test_api_ingest_query_sse_reload_and_feedback(tmp_path: Path) -> None:
    container = make_container(tmp_path)
    with TestClient(create_app(container)) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/catalogs/ingest", json={"dataset": "olist"}).status_code == 201
        response = client.post(
            "/queries",
            json={"db_id": "olist", "question": "Count orders", "correction_enabled": False},
        )
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        with client.stream("GET", f"/queries/{run_id}/events") as stream:
            body = "".join(stream.iter_text())
        assert "event: terminal" in body
        assert all(f'"layer":"{layer}"' in body for layer in range(1, 7))
        persisted = client.get(f"/queries/{run_id}").json()
        assert persisted["status"] == "COMPLETED"
        assert persisted["result"]["run_id"] == run_id
        assert persisted["config"]["correction_enabled"] is False
        assert persisted["config"]["max_result_rows"] == 200
        trace = client.get(f"/queries/{run_id}/trace")
        assert trace.status_code == 200
        assert [event["layer"] for event in trace.json()] == [str(i) for i in range(7)]
        feedback = client.post(
            "/feedback", json={"run_id": run_id, "rating": "CORRECT", "categories": []}
        )
        assert feedback.status_code == 201
    container.close()

    reloaded = ApplicationContainer(container.settings)
    reloaded.query_service.runtime_factory = lambda *args, **kwargs: FakeRuntime()
    with TestClient(create_app(reloaded)) as client:
        persisted = client.get(f"/queries/{run_id}")
        assert persisted.status_code == 200
        assert persisted.json()["result"]["run_id"] == run_id
        replay = client.get(f"/queries/{run_id}/trace").json()
        assert [event["layer"] for event in replay] == [str(i) for i in range(7)]
    reloaded.close()


def test_api_rejects_arbitrary_ingest_and_unknown_database(tmp_path: Path) -> None:
    container = make_container(tmp_path)
    with TestClient(create_app(container)) as client:
        assert client.post("/catalogs/ingest", json={"dataset": "/tmp/evil.db"}).status_code == 422
        response = client.post(
            "/queries", json={"db_id": "unknown", "question": "Count", "correction_enabled": False}
        )
        assert response.status_code == 404
    container.close()
