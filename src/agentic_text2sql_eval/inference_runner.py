"""Gold-blind inference runner for the Phase 2 direct baseline."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.contracts.sql import DirectRunResult, DirectStatus
from agentic_text2sql.layer6_application.query_service import DirectBaselineService


class SmokeCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    language: str
    question: str
    expected_status: DirectStatus
    gold_sql: str | None = None
    semantic_tags: list[str] = Field(default_factory=list)


class SmokePrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    result: DirectRunResult


def load_smoke_cases(path: Path) -> list[SmokeCase]:
    return [
        SmokeCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_inference(
    *,
    cases: list[SmokeCase],
    service: DirectBaselineService,
    database: Path,
    catalog: CatalogSnapshot,
    prediction_path: Path,
    initial_predictions: list[SmokePrediction] | None = None,
    max_new_cases: int | None = None,
) -> list[SmokePrediction]:
    """Pass only question text to runtime; gold fields remain outside its state."""
    predictions = list(initial_predictions or [])
    expected_prefix = [case.id for case in cases[: len(predictions)]]
    if [prediction.case_id for prediction in predictions] != expected_prefix:
        raise ValueError("Existing predictions are not a valid manifest prefix")
    prediction_path.parent.mkdir(parents=True, exist_ok=True)
    remaining = cases[len(predictions) :]
    if max_new_cases is not None:
        if max_new_cases < 1:
            raise ValueError("max_new_cases must be positive")
        remaining = remaining[:max_new_cases]
    for index, case in enumerate(remaining, start=len(predictions) + 1):
        prediction = SmokePrediction(
            case_id=case.id,
            result=service.run(case.question, database, catalog),
        )
        predictions.append(prediction)
        temporary = prediction_path.with_suffix(f"{prediction_path.suffix}.tmp")
        temporary.write_text(
            "\n".join(item.model_dump_json() for item in predictions) + "\n",
            encoding="utf-8",
        )
        temporary.replace(prediction_path)
        print(f"inference {index}/{len(cases)} {case.id}: {prediction.result.status.value}")
    return predictions
