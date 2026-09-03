from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import TracebackType

from fastapi.testclient import TestClient

from agentic_text2sql.contracts.planning import (
    AnswerabilityDecision,
    AnswerabilityOutcome,
    ClarificationContext,
    ClarificationOption,
    Interpretation,
    QuestionCategory,
)
from agentic_text2sql.contracts.sql import DirectRunResult, DirectStatus
from agentic_text2sql.contracts.trace import RunStatus
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

    def run(
        self,
        question: str,
        database: Path,
        catalog: object,
        *,
        clarification_context: ClarificationContext | None = None,
    ) -> DirectRunResult:
        del database, catalog
        return DirectRunResult(
            run_id="runtime",
            question=question,
            status=DirectStatus.SUCCEEDED,
            route_reason="query",
            prompt_versions={},
            clarification_context=clarification_context,
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
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["correction_default"] is True
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
        default_response = client.post(
            "/queries", json={"db_id": "olist", "question": "Count orders again"}
        )
        assert default_response.status_code == 202
        default_run_id = default_response.json()["run_id"]
        with client.stream("GET", f"/queries/{default_run_id}/events") as stream:
            assert "event: terminal" in "".join(stream.iter_text())
        default_run = client.get(f"/queries/{default_run_id}").json()
        assert default_run["config"]["correction_enabled"] is True
        summaries = client.get("/queries", params={"include_result": False}).json()
        summary = next(item for item in summaries if item["run_id"] == run_id)
        assert summary["result"] is None
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


def test_api_links_clarification_follow_up_to_parent_run(tmp_path: Path) -> None:
    container = make_container(tmp_path)
    with TestClient(create_app(container)) as client:
        assert client.post("/catalogs/ingest", json={"dataset": "olist"}).status_code == 201
        options = (
            ClarificationOption(option_id="o1", label="Placed orders"),
            ClarificationOption(option_id="o2", label="Delivered orders"),
        )
        parent = container.runs.create("clarify-parent", "olist", "How many recent orders?")
        decision = AnswerabilityDecision(
            outcome=AnswerabilityOutcome.CLARIFY,
            reason_code=QuestionCategory.AMBIGUOUS_FILTER_CRITERIA,
            rationale="Recent needs a reporting definition.",
            interpretations=(
                Interpretation(interpretation_id="i1", business_label="Placed orders"),
                Interpretation(interpretation_id="i2", business_label="Delivered orders"),
            ),
            clarification_question="Which order population?",
            clarification_options=options,
            source="local_llm",
        )
        result = DirectRunResult(
            run_id=parent.run_id,
            question=parent.question,
            status=DirectStatus.CLARIFY,
            route_reason=decision.rationale,
            prompt_versions={"question_analyst": "question_analyst_v1"},
            answerability=decision,
        )
        container.runs.set_status(
            parent.run_id, RunStatus.COMPLETED, result.model_dump(mode="json")
        )

        response = client.post(
            "/queries",
            json={
                "db_id": "olist",
                "question": "Delivered orders",
                "clarification_run_id": parent.run_id,
                "correction_enabled": False,
            },
        )
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        with client.stream("GET", f"/queries/{run_id}/events") as stream:
            assert "event: terminal" in "".join(stream.iter_text())
        persisted = client.get(f"/queries/{run_id}").json()
        assert persisted["parent_run_id"] == parent.run_id
        assert persisted["result"]["clarification_context"]["user_response"] == "Delivered orders"
    container.close()


def test_report_api_exposes_release_summary_without_details(tmp_path: Path) -> None:
    container = make_container(tmp_path)
    reports = tmp_path / "evals/reports"
    reports.mkdir(parents=True)
    (reports / "spider-release.json").write_text(
        json.dumps(
            {
                "evaluation_id": "spider-dev-stratified-200-p6-v1",
                "benchmark_kind": "cross-domain-execution-laptop-stratified",
                "release_status": "complete",
                "case_count": 200,
                "result_accuracy": 0.5,
                "failure_categories": {"EXECUTION_MISMATCH": 10},
                "details": [{"generated_sql": "SELECT private_debug_value"}],
            }
        ),
        encoding="utf-8",
    )
    with TestClient(create_app(container)) as client:
        listed = client.get("/reports").json()
        assert listed[0]["release_status"] == "complete"
        report = client.get("/reports/spider-release").json()
        assert "details" not in report
        assert report["failure_categories"] == {"EXECUTION_MISMATCH": 10}
    container.close()
