"""Phase 0 CLI entrypoint."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel, ConfigDict, Field

from agentic_text2sql.adapters.llm.ollama_provider import OllamaProvider
from agentic_text2sql.data.olist import (
    build_olist_database,
    default_olist_paths,
    download_olist,
    extract_and_verify_source,
    load_source_manifest,
    validate_olist_database,
)
from agentic_text2sql.doctor import run_doctor
from agentic_text2sql.exceptions import Text2SQLError
from agentic_text2sql.layer6_application.catalog_registry import CatalogRegistry
from agentic_text2sql.layer6_application.run_store import SQLiteRunStore
from agentic_text2sql.layer6_application.service import ApplicationQueryService
from agentic_text2sql.layer6_application.service_factory import runtime_bundle
from agentic_text2sql.settings import Settings

app = typer.Typer(no_args_is_help=True, help="Fully local agentic text-to-SQL tooling.")
data_app = typer.Typer(no_args_is_help=True, help="Dataset download/build/validation commands.")
trace_app = typer.Typer(no_args_is_help=True, help="Inspect persisted six-layer traces.")
app.add_typer(data_app, name="data")
app.add_typer(trace_app, name="trace")


def _application() -> tuple[ApplicationQueryService, CatalogRegistry, SQLiteRunStore]:
    settings = Settings()
    state = settings.resolved_artifact_dir / "application.sqlite"
    registry = CatalogRegistry(state)
    runs = SQLiteRunStore(state)
    return ApplicationQueryService(settings, registry, runs, runtime_bundle), registry, runs


class SmokeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: str
    sql: str = Field(pattern=r"(?is)^\s*select\b")
    read_only: bool


@app.command()
def doctor(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Check paths, hardware, Ollama, and the configured local model."""
    report = run_doctor()
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        for check in report.checks:
            typer.echo(f"{check.status.value:4} {check.name}: {check.detail}")
    if not report.passed:
        raise typer.Exit(code=1)


@app.command("ollama-smoke")
def ollama_smoke() -> None:
    """Prove Vietnamese + JSON Schema + SQLite SQL structured generation."""
    prompt = (
        "Trả lời bằng JSON theo schema. Viết SQLite SQL chỉ đọc để trả về số 1 với alias "
        "ket_qua. Đặt language='vi' và read_only=true. Không dùng markdown."
    )
    try:
        with OllamaProvider() as provider:
            response = provider.generate_structured(prompt=prompt, response_model=SmokeResponse)
    except Text2SQLError as exc:
        typer.echo(f"FAIL structured smoke: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(response.model_dump(), ensure_ascii=False, indent=2))


@data_app.command("download")
def data_download(dataset: str = typer.Argument()) -> None:
    """Download and verify a pinned dataset snapshot."""
    if dataset != "olist":
        typer.echo(f"Unsupported dataset: {dataset}", err=True)
        raise typer.Exit(code=2)
    paths = default_olist_paths()
    manifest = load_source_manifest(paths["manifest"])
    archive = download_olist(paths["archive"], manifest)
    verification = extract_and_verify_source(archive, paths["raw_dir"], manifest)
    typer.echo(verification.model_dump_json(indent=2))


@data_app.command("build")
def data_build(dataset: str = typer.Argument()) -> None:
    """Build a validated SQLite database atomically from pinned raw files."""
    if dataset != "olist":
        typer.echo(f"Unsupported dataset: {dataset}", err=True)
        raise typer.Exit(code=2)
    paths = default_olist_paths()
    report = build_olist_database(
        raw_dir=paths["raw_dir"],
        output=paths["database"],
        manifest_path=paths["manifest"],
        schema_path=paths["schema"],
        indexes_path=paths["indexes"],
        views_path=paths["views"],
    )
    typer.echo(report.model_dump_json(indent=2))


@data_app.command("validate")
def data_validate(dataset: str = typer.Argument()) -> None:
    """Run Olist integrity, anomaly, and semantic-invariant checks."""
    if dataset != "olist":
        typer.echo(f"Unsupported dataset: {dataset}", err=True)
        raise typer.Exit(code=2)
    paths = default_olist_paths()
    report = validate_olist_database(paths["database"], paths["expected_counts"])
    typer.echo(report.model_dump_json(indent=2))
    if not report.passed:
        raise typer.Exit(code=1)


@app.command()
def ingest(
    database: Annotated[Path, typer.Option("--db", exists=True, dir_okay=False)],
    db_id: Annotated[str, typer.Option("--db-id")],
) -> None:
    """Register and introspect one local SQLite database for later queries."""
    _, registry, _ = _application()
    try:
        catalog = registry.register(db_id, database)
    except (OSError, ValueError) as exc:
        typer.echo(f"FAIL ingest: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(catalog.model_dump_json(indent=2))


@app.command()
def ask(
    db_id: Annotated[str, typer.Option("--db-id")],
    question: Annotated[str, typer.Option("--question")],
    correction: Annotated[bool, typer.Option("--correction/--no-correction")] = False,
) -> None:
    """Run the shared read-only workflow and persist its trace."""
    service, _, _ = _application()
    try:
        record = service.run(db_id, question, correction_enabled=correction)
    except (KeyError, OSError, ValueError, Text2SQLError) as exc:
        typer.echo(f"FAIL query: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(record.result, ensure_ascii=False, indent=2))


@trace_app.command("show")
def trace_show(run_id: str) -> None:
    """Show one persisted run and all six layer events."""
    _, _, runs = _application()
    try:
        record = runs.get(run_id)
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    payload = {
        "run": record.model_dump(mode="json"),
        "events": [item.model_dump(mode="json") for item in runs.events(run_id)],
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = typer.Option(8000, min=1, max=65535),
) -> None:
    """Start the local FastAPI service; never bind publicly by default."""
    import uvicorn

    uvicorn.run(
        "agentic_text2sql.interfaces.api.app:create_app",
        factory=True,
        host=host,
        port=port,
    )


if __name__ == "__main__":
    app()
