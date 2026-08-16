import sqlite3
from pathlib import Path

import pytest

from agentic_text2sql.contracts.trace import RunStatus, TraceEvent
from agentic_text2sql.layer6_application.catalog_registry import CatalogRegistry
from agentic_text2sql.layer6_application.run_store import SQLiteRunStore


def test_run_and_six_layer_trace_survive_store_restart(tmp_path: Path) -> None:
    path = tmp_path / "application.sqlite"
    store = SQLiteRunStore(path)
    store.create("run-1", "tiny", "Count orders", {"correction_enabled": False})
    store.set_status("run-1", RunStatus.RUNNING)
    for layer in range(1, 7):
        saved = store.append_event(
            TraceEvent(
                run_id="run-1",
                layer=str(layer),
                event="DONE",
                elapsed_ms=float(layer),
            )
        )
        assert saved.sequence == layer
    store.set_status("run-1", RunStatus.COMPLETED, {"status": "SUCCEEDED"})

    reloaded = SQLiteRunStore(path)
    assert reloaded.get("run-1").result == {"status": "SUCCEEDED"}
    assert reloaded.get("run-1").config == {"correction_enabled": False}
    reloaded.update_config("run-1", {"model_digest": "abc"})
    assert reloaded.get("run-1").config == {
        "correction_enabled": False,
        "model_digest": "abc",
    }
    assert [event.layer for event in reloaded.events("run-1")] == [str(i) for i in range(1, 7)]


def test_catalog_registry_rejects_invalid_identifiers_and_missing_paths(tmp_path: Path) -> None:
    registry = CatalogRegistry(tmp_path / "registry.sqlite")
    with pytest.raises(ValueError):
        registry.register("../../escape", tmp_path / "missing.sqlite")
    with pytest.raises(KeyError):
        registry.resolve("unknown")
    database = tmp_path / "missing.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sample(id INTEGER)")
    registry.register("missing", database)
    database.unlink()
    with pytest.raises(FileNotFoundError):
        registry.resolve("missing")


def test_run_search_escapes_sql_wildcards(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "application.sqlite")
    store.create("one", "tiny", "100% revenue")
    store.create("two", "tiny", "100 orders")
    assert [item.run_id for item in store.list(query="100%")] == ["one"]


def test_run_list_can_omit_heavy_results(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "application.sqlite")
    store.create("one", "tiny", "Count")
    store.set_status("one", RunStatus.COMPLETED, {"result_rows": [[1] for _ in range(200)]})

    assert store.list(include_result=False)[0].result is None
    assert store.get("one").result is not None


def test_restart_fails_incomplete_work_closed_and_keeps_trace(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "application.sqlite")
    store.create("queued", "tiny", "Count")
    store.create("running", "tiny", "Sum")
    store.set_status("running", RunStatus.RUNNING)

    assert store.recover_incomplete() == ["queued", "running"]
    assert store.get("queued").status is RunStatus.FAILED
    assert store.get("running").result == {
        "run_id": "running",
        "status": "APPLICATION_RESTARTED",
        "safe_message": "The local process restarted before this run completed.",
    }
    assert store.events("running")[-1].event == "APPLICATION_RESTARTED"
