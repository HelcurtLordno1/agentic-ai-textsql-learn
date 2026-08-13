"""FastAPI factory for the fully local application boundary."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agentic_text2sql.interfaces.api.dependencies import ApplicationContainer
from agentic_text2sql.interfaces.api.routes import catalogs, feedback, health, queries, reports


def create_app(container: ApplicationContainer | None = None) -> FastAPI:
    owned = container is None
    resolved = container or ApplicationContainer()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if owned:
            resolved.close()

    app = FastAPI(
        title="Local Agentic Text-to-SQL",
        version="0.1.0",
        description="Read-only, traceable, fully local Text-to-SQL API.",
        lifespan=lifespan,
    )
    app.state.container = resolved
    app.include_router(health.router)
    app.include_router(catalogs.router)
    app.include_router(queries.router)
    app.include_router(feedback.router)
    app.include_router(reports.router)
    return app
