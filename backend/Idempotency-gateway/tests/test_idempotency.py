import httpx
import pytest

from app.config import Settings
from app.main import create_app

pytestmark = pytest.mark.anyio


async def test_replay_returns_saved_bytes_without_processing(client, processor):
    arguments = {
        "headers": {"Idempotency-Key": "replay-payment"},
        "json": {"amount": 100, "currency": "GHS"},
    }
    first = await client.post("/process-payment", **arguments)
    replay = await client.post("/process-payment", **arguments)

    assert first.status_code == replay.status_code == 201
    assert first.content == replay.content
    assert first.headers["X-Cache-Hit"] == "false"
    assert replay.headers["X-Cache-Hit"] == "true"
    assert processor.calls == 1


@pytest.mark.parametrize(
    "body",
    [
        b'{"currency":"GHS","amount":100}',
        b'{"amount":100.0,"currency":"GHS"}',
        b'{ "currency": "GHS", "amount": 100.00 }',
    ],
)
async def test_equivalent_payloads_replay(client, processor, body):
    headers = {"Idempotency-Key": "canonical-payment", "Content-Type": "application/json"}
    first = await client.post(
        "/process-payment", headers=headers, json={"amount": 100, "currency": "GHS"}
    )
    replay = await client.post("/process-payment", headers=headers, content=body)

    assert first.status_code == replay.status_code == 201
    assert first.content == replay.content
    assert replay.headers["X-Cache-Hit"] == "true"
    assert processor.calls == 1


async def test_surrounding_key_whitespace_is_normalized(client, processor):
    first = await client.post(
        "/process-payment",
        headers={"Idempotency-Key": "  trimmed-key  "},
        json={"amount": 100, "currency": "GHS"},
    )
    replay = await client.post(
        "/process-payment",
        headers={"Idempotency-Key": "trimmed-key"},
        json={"amount": 100, "currency": "GHS"},
    )

    assert first.status_code == replay.status_code == 201
    assert first.content == replay.content
    assert replay.headers["X-Cache-Hit"] == "true"
    assert processor.calls == 1


async def test_new_app_has_its_own_store(client, processor):
    headers = {"Idempotency-Key": "process-local-payment"}
    body = {"amount": 100, "currency": "GHS"}
    first = await client.post("/process-payment", headers=headers, json=body)
    another_app = create_app(Settings(processing_delay_seconds=0), processor=processor)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=another_app), base_url="http://test"
    ) as another_client:
        second = await another_client.post("/process-payment", headers=headers, json=body)

    assert first.status_code == second.status_code == 201
    assert second.headers["X-Cache-Hit"] == "false"
    assert first.json()["transaction_id"] != second.json()["transaction_id"]
    assert processor.calls == 2
