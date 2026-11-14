import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.processor import PaymentProcessor


class SpyProcessor(PaymentProcessor):
    def __init__(self):
        super().__init__(delay_seconds=0)
        self.calls = 0

    async def charge(self, payment):
        self.calls += 1
        return await super().charge(payment)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def processor():
    return SpyProcessor()


@pytest.fixture
def app(processor):
    return create_app(settings=Settings(processing_delay_seconds=0), processor=processor)


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
