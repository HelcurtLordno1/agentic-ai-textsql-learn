"""Read-only access to generated benchmark reports; never exposes benchmark configs/gold SQL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException

from agentic_text2sql.interfaces.api.dependencies import ApplicationContainer, get_container

router = APIRouter(prefix="/reports", tags=["reports"])
ContainerDep = Annotated[ApplicationContainer, Depends(get_container)]


def _report_root(container: ApplicationContainer) -> Path:
    return container.settings.project_root / "evals/reports"


@router.get("")
def list_reports(container: ContainerDep) -> list[dict[str, object]]:
    reports = []
    for path in sorted(_report_root(container).glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        reports.append(
            {
                "report_id": path.stem,
                "evaluation_id": payload.get("evaluation_id", path.stem),
                "case_count": payload.get("case_count"),
                "result_accuracy": payload.get("result_accuracy"),
                "workflow_completion_rate": payload.get("workflow_completion_rate"),
                "latency_ms": payload.get("latency_ms"),
            }
        )
    return reports


@router.get("/{report_id}")
def get_report(report_id: str, container: ContainerDep) -> dict[str, object]:
    if not report_id.replace("-", "_").isalnum():
        raise HTTPException(status_code=400, detail="Invalid report id")
    path = _report_root(container) / f"{report_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    payload = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    payload.pop("details", None)
    return payload
