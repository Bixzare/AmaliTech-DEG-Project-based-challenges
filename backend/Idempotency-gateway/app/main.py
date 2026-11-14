"""Application factory and Uvicorn entry point."""

import time
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router
from app.config import Settings
from app.processor import PaymentProcessor
from app.store import IdempotencyStore


def create_app(
    settings: Settings | None = None,
    processor: PaymentProcessor | None = None,
    clock: Callable[[], float] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            await app.state.store.drain()

    app = FastAPI(title="Idempotency Gateway", lifespan=lifespan)
    app.state.settings = settings if settings is not None else Settings.from_env()
    app.state.processor = processor if processor is not None else PaymentProcessor(
        app.state.settings.processing_delay_seconds
    )
    app.state.store = IdempotencyStore(
        ttl_seconds=app.state.settings.idempotency_ttl_seconds,
        clock=clock if clock is not None else time.monotonic,
    )
    app.include_router(router)
    return app


app = create_app()
