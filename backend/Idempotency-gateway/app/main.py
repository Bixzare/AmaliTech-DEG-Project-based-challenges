"""Application factory and Uvicorn entry point."""

from fastapi import FastAPI

from app.api import router
from app.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Idempotency Gateway")
    app.state.settings = settings if settings is not None else Settings.from_env()
    app.include_router(router)
    return app


app = create_app()
