"""Human feedback endpoint with no automatic learning side effect."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from agentic_text2sql.interfaces.api.dependencies import ApplicationContainer, get_container
from agentic_text2sql.interfaces.api.schemas import FeedbackRequest

router = APIRouter(prefix="/feedback", tags=["feedback"])
ContainerDep = Annotated[ApplicationContainer, Depends(get_container)]


@router.post("", status_code=201)
def create_feedback(
    request: FeedbackRequest,
    container: ContainerDep,
) -> dict[str, object]:
    try:
        container.runs.get(request.run_id)
        record = container.feedback.add(
            request.run_id, request.rating, request.categories, request.note
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record.model_dump(mode="json")
