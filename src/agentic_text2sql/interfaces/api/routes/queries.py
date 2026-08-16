"""Asynchronous local query endpoints and restart-safe event streaming."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from agentic_text2sql.contracts.trace import RunStatus, TraceEvent
from agentic_text2sql.interfaces.api.dependencies import ApplicationContainer, get_container
from agentic_text2sql.interfaces.api.schemas import QueryAccepted, QueryRequest, QueryResponse

router = APIRouter(prefix="/queries", tags=["queries"])
ContainerDep = Annotated[ApplicationContainer, Depends(get_container)]


def _response(record: object) -> QueryResponse:
    return QueryResponse.model_validate(record, from_attributes=True)


@router.post("", status_code=202)
def create_query(
    request: QueryRequest,
    container: ContainerDep,
) -> QueryAccepted:
    try:
        run_id = container.submit(request.db_id, request.question, request.correction_enabled)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return QueryAccepted(
        run_id=run_id,
        status=RunStatus.QUEUED,
        events_url=f"/queries/{run_id}/events",
    )


@router.get("")
def list_queries(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    status: RunStatus | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    include_result: bool = True,
) -> list[QueryResponse]:
    records = container.runs.list(
        limit=limit, status=status, query=search, include_result=include_result
    )
    return [_response(item) for item in records]


@router.get("/{run_id}")
def get_query(run_id: str, container: ContainerDep) -> QueryResponse:
    try:
        return _response(container.runs.get(run_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{run_id}/events")
def query_events(
    run_id: str,
    container: ContainerDep,
    after: Annotated[int, Query(ge=0)] = 0,
) -> StreamingResponse:
    try:
        container.runs.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def stream() -> AsyncIterator[str]:
        cursor = after
        while True:
            for event in container.runs.events(run_id, after=cursor):
                cursor = event.sequence
                yield f"id: {cursor}\nevent: trace\ndata: {event.model_dump_json()}\n\n"
            record = container.runs.get(run_id)
            if record.status in {RunStatus.COMPLETED, RunStatus.FAILED}:
                payload = json.dumps({"status": record.status.value})
                yield f"event: terminal\ndata: {payload}\n\n"
                break
            yield ": keep-alive\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/{run_id}/trace")
def query_trace(run_id: str, container: ContainerDep) -> list[TraceEvent]:
    """Return the persisted trace without waiting for a running query to finish."""
    try:
        container.runs.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return container.runs.events(run_id)
