from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from agentic_text2sql.interfaces.cli.app import app


def test_cli_ingest_and_trace_persist_across_invocations(tmp_path: Path) -> None:
    database = tmp_path / "tiny.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE orders(id INTEGER PRIMARY KEY)")
    artifacts = tmp_path / "artifacts"
    environment = {
        "PROJECT_ROOT": str(tmp_path),
        "TEXT2SQL_DATA_DIR": str(tmp_path / "data"),
        "TEXT2SQL_ARTIFACT_DIR": str(artifacts),
    }
    runner = CliRunner()
    ingested = runner.invoke(
        app,
        ["ingest", "--db", str(database), "--db-id", "tiny"],
        env=environment,
    )
    assert ingested.exit_code == 0, ingested.output
    assert json.loads(ingested.output)["db_id"] == "tiny"

    unknown = runner.invoke(app, ["trace", "show", "missing"], env=environment)
    assert unknown.exit_code == 2
    assert "Unknown run: missing" in unknown.output
