"""Deterministic presentation hints; no extra model call or semantic invention."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from agentic_text2sql.contracts.sql import DirectRunResult, DirectStatus


class Presentation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    headline: str
    tone: Literal["success", "corrected", "clarify", "blocked", "error"]
    visualization: Literal["kpi", "bar", "line", "table", "none"]
    rows: list[list[Any]]


def present_result(result: DirectRunResult) -> Presentation:
    if result.status is DirectStatus.SUCCEEDED:
        corrected = bool(result.correction and result.correction.get("recovered"))
        row_count = len(result.result_rows)
        column_count = len(result.result_columns)
        visualization: Literal["kpi", "bar", "line", "table", "none"] = "table"
        if row_count == column_count == 1:
            visualization = "kpi"
        elif row_count > 1 and column_count == 2:
            first = result.result_rows[0] if result.result_rows else []
            visualization = "line" if first and _looks_temporal(first[0]) else "bar"
        return Presentation(
            headline=("Corrected safely" if corrected else "Query completed"),
            tone="corrected" if corrected else "success",
            visualization=visualization,
            rows=result.result_rows,
        )
    if result.status is DirectStatus.CLARIFY:
        return Presentation(
            headline="More detail is needed", tone="clarify", visualization="none", rows=[]
        )
    if result.status in {DirectStatus.WRITE_BLOCKED, DirectStatus.POLICY_BLOCKED}:
        return Presentation(
            headline="Request blocked safely", tone="blocked", visualization="none", rows=[]
        )
    return Presentation(
        headline="Query could not be completed", tone="error", visualization="none", rows=[]
    )


def _looks_temporal(value: object) -> bool:
    text = str(value)
    return len(text) >= 7 and text[:4].isdigit() and text[4] in {"-", "/"}
