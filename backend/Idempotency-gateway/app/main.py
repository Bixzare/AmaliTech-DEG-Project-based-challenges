"""Application factory and Uvicorn entry point."""

import asyncio
import time
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api import router, simulation_router
from app.config import Settings
from app.processor import PaymentProcessor
from app.store import IdempotencyStore


def create_app(
    settings: Settings | None = None,
    processor: PaymentProcessor | None = None,
    clock: Callable[[], float] | None = None,
) -> FastAPI:
    async def sweep_expired(app: FastAPI) -> None:
        while True:
            await asyncio.sleep(app.state.settings.idempotency_sweep_interval_seconds)
            app.state.store.purge_expired()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        sweeper = asyncio.create_task(sweep_expired(app))
        app.state.sweeper_task = sweeper
        try:
            yield
        finally:
            sweeper.cancel()
            try:
                with suppress(asyncio.CancelledError):
                    await sweeper
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
    if app.state.settings.simulation_controls_enabled:
        app.include_router(simulation_router)
    return app


app = create_app()
