from datetime import datetime
from uuid import UUID

import pytest

pytestmark = pytest.mark.anyio


async def test_health(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "amount,message",
    [(100, "Charged 100 GHS"), (100.50, "Charged 100.50 GHS"), (100.00, "Charged 100 GHS")],
)
async def test_first_payment(client, processor, amount, message):
    response = await client.post(
        "/process-payment",
        headers={"Idempotency-Key": "first-payment"},
        json={"amount": amount, "currency": "GHS"},
    )

    assert response.status_code == 201
    assert response.headers["X-Cache-Hit"] == "false"
    body = response.json()
    assert body["status"] == "success"
    assert body["message"] == message
    assert UUID(body["transaction_id"]).version == 4
    assert body["processed_at"].endswith("Z")
    assert datetime.fromisoformat(body["processed_at"]).utcoffset().total_seconds() == 0
    assert processor.calls == 1


async def test_different_keys_make_separate_charges(client, processor):
    responses = [
        await client.post(
            "/process-payment",
            headers={"Idempotency-Key": key},
            json={"amount": 100, "currency": "GHS"},
        )
        for key in ("payment-a", "payment-b")
    ]

    assert all(response.status_code == 201 for response in responses)
    assert responses[0].json()["transaction_id"] != responses[1].json()["transaction_id"]
    assert processor.calls == 2


@pytest.mark.parametrize("key", [None, "", "   ", "x" * 256])
async def test_invalid_key(client, processor, key):
    response = await client.post(
        "/process-payment",
        headers={} if key is None else {"Idempotency-Key": key},
        json={"amount": 100, "currency": "GHS"},
    )

    assert response.status_code == 400
    assert "Idempotency-Key" in response.json()["detail"]
    assert "X-Cache-Hit" not in response.headers
    assert processor.calls == 0


async def test_maximum_key_length_after_trimming(client):
    response = await client.post(
        "/process-payment",
        headers={"Idempotency-Key": "  " + "x" * 255 + "  "},
        json={"amount": 100, "currency": "GHS"},
    )

    assert response.status_code == 201


@pytest.mark.parametrize(
    "body",
    [
        {"amount": -1, "currency": "GHS"},
        {"amount": 0, "currency": "GHS"},
        {"amount": 1.001, "currency": "GHS"},
        {"amount": "12345678901.23", "currency": "GHS"},
        {"amount": "NaN", "currency": "GHS"},
        {"amount": "Infinity", "currency": "GHS"},
        {"amount": 100, "currency": "ghs"},
        {"amount": 100, "currency": "GH"},
        {"amount": 100, "currency": "GHS", "extra": True},
        {"currency": "GHS"},
        {"amount": 100},
    ],
)
async def test_invalid_body_does_not_consume_key(client, processor, body):
    headers = {"Idempotency-Key": "fixable-payment"}
    invalid = await client.post("/process-payment", headers=headers, json=body)

    assert invalid.status_code == 422
    assert "X-Cache-Hit" not in invalid.headers
    assert processor.calls == 0

    valid = await client.post(
        "/process-payment", headers=headers, json={"amount": 100, "currency": "GHS"}
    )

    assert valid.status_code == 201
    assert valid.headers["X-Cache-Hit"] == "false"
    assert processor.calls == 1
