"""Catalog endpoints constrained to the server-side dataset registry."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from agentic_text2sql.interfaces.api.dependencies import ApplicationContainer, get_container
from agentic_text2sql.interfaces.api.schemas import CatalogIngestRequest

router = APIRouter(prefix="/catalogs", tags=["catalogs"])
ContainerDep = Annotated[ApplicationContainer, Depends(get_container)]


@router.get("")
def list_catalogs(container: ContainerDep) -> list[dict[str, object]]:
    return [catalog.model_dump(mode="json") for catalog in container.registry.list()]


@router.post("/ingest", status_code=201)
def ingest_catalog(
    request: CatalogIngestRequest,
    container: ContainerDep,
) -> dict[str, object]:
    db_id, path = container.dataset_path(request.dataset)
    if not path.is_file():
        raise HTTPException(status_code=409, detail="Dataset database has not been built")
    catalog = container.registry.register(db_id, path)
    return catalog.model_dump(mode="json")
