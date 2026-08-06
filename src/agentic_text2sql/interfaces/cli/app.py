"""Phase 0 CLI entrypoint."""

from __future__ import annotations

import json
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

app = typer.Typer(no_args_is_help=True, help="Fully local agentic text-to-SQL tooling.")
data_app = typer.Typer(no_args_is_help=True, help="Dataset download/build/validation commands.")
app.add_typer(data_app, name="data")


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


if __name__ == "__main__":
    app()
