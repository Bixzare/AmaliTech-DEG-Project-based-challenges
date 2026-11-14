import asyncio

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.processor import PaymentProcessingError, PaymentProcessor


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class SpyProcessor(PaymentProcessor):
    def __init__(self):
        super().__init__(delay_seconds=0)
        self.calls = 0
        self.charge_tasks = []
        self.gated = False
        self.fail = False
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def charge(self, payment):
        self.calls += 1
        self.charge_tasks.append(asyncio.current_task())
        self.started.set()
        if self.gated:
            await self.release.wait()
        if self.fail:
            raise PaymentProcessingError("Simulated test failure")
        return await super().charge(payment)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def processor():
    return SpyProcessor()


@pytest.fixture
def fake_clock():
    return FakeClock()


@pytest.fixture
def app(processor):
    return create_app(settings=Settings(processing_delay_seconds=0), processor=processor)


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
