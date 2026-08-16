"""Local readiness endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from agentic_text2sql.interfaces.api.dependencies import ApplicationContainer, get_container

router = APIRouter(tags=["system"])
ContainerDep = Annotated[ApplicationContainer, Depends(get_container)]


@router.get("/health")
def health(container: ContainerDep) -> dict[str, object]:
    return {
        "status": "ok",
        "environment": "local",
        "registered_catalogs": len(container.registry.list()),
        "correction_default": True,
    }


@router.get("/models")
def models(container: ContainerDep) -> dict[str, object]:
    return {
        "generation": container.settings.ollama_model,
        "embedding": "bge-m3:latest",
        "base_url": container.settings.ollama_base_url,
    }
