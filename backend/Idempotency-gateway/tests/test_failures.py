import asyncio

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.processor import PaymentProcessingError, PaymentProcessor
from app.schemas import PaymentRequest

pytestmark = pytest.mark.anyio

PAYMENT = {"amount": 100, "currency": "GHS"}
CONTROL = "/simulation/fail-next-charges"
FAILURE_BODY = {
    "detail": "Payment processing failed. No charge was made; retry with the same Idempotency-Key."
}


@pytest.fixture
async def real_client():
    app = create_app(Settings(processing_delay_seconds=0))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def pay(client, key="retryable-payment"):
    return await client.post(
        "/process-payment", headers={"Idempotency-Key": key}, json=PAYMENT
    )


async def test_failure_releases_key_and_retry_is_processed(client, processor):
    processor.fail = True
    failed = await pay(client)

    assert failed.status_code == 502
    assert failed.json() == FAILURE_BODY
    assert "X-Cache-Hit" not in failed.headers
    assert processor.calls == 1

    processor.fail = False
    retry = await pay(client)
    replay = await pay(client)

    assert retry.status_code == replay.status_code == 201
    assert retry.headers["X-Cache-Hit"] == "false"
    assert replay.headers["X-Cache-Hit"] == "true"
    assert replay.content == retry.content
    assert processor.calls == 2


async def test_concurrent_waiters_share_one_failed_charge(client, app, processor, monkeypatch):
    processor.gated = True
    processor.fail = True
    all_arrived = asyncio.Event()
    execute = app.state.store.execute
    arrivals = 0

    async def observed(*args, **kwargs):
        nonlocal arrivals
        arrivals += 1
        if arrivals == 5:
            all_arrived.set()
        return await execute(*args, **kwargs)

    monkeypatch.setattr(app.state.store, "execute", observed)
    requests = []
    try:
        async with asyncio.timeout(3):
            requests.append(asyncio.create_task(pay(client)))
            await processor.started.wait()
            requests.extend(asyncio.create_task(pay(client)) for _ in range(4))
            await all_arrived.wait()
            assert all(not request.done() for request in requests)
            assert processor.calls == 1
            processor.release.set()
            responses = await asyncio.gather(*requests)

        assert all(response.status_code == 502 for response in responses)
        assert all(response.json() == FAILURE_BODY for response in responses)
        assert all("X-Cache-Hit" not in response.headers for response in responses)
        assert processor.calls == 1

        processor.fail = False
        retry = await pay(client)
        assert retry.status_code == 201
        assert retry.headers["X-Cache-Hit"] == "false"
        assert processor.calls == 2
    finally:
        processor.release.set()
        await asyncio.gather(*requests, return_exceptions=True)


async def test_manual_failure_then_same_key_retry_without_restart(real_client):
    control = await real_client.post(CONTROL, json={"count": 1})
    assert control.status_code == 200
    assert control.json() == {"failures_pending": 1}

    failed = await pay(real_client)
    assert failed.status_code == 502
    assert failed.json() == FAILURE_BODY
    assert "X-Cache-Hit" not in failed.headers

    retry = await pay(real_client)
    assert retry.status_code == 201
    assert retry.headers["X-Cache-Hit"] == "false"
    assert (await pay(real_client, "another-payment")).status_code == 201


async def test_failure_control_replaces_count_and_zero_clears_it(real_client):
    for count in (3, 1):
        control = await real_client.post(CONTROL, json={"count": count})
        assert control.status_code == 200
        assert control.json() == {"failures_pending": count}

    assert (await pay(real_client)).status_code == 502
    assert (await pay(real_client)).status_code == 201

    await real_client.post(CONTROL, json={"count": 1})
    cleared = await real_client.post(CONTROL, json={"count": 0})
    assert cleared.json() == {"failures_pending": 0}
    assert (await pay(real_client, "after-clear")).status_code == 201


async def test_replay_does_not_consume_pending_failure(real_client):
    first = await pay(real_client)
    await real_client.post(CONTROL, json={"count": 1})
    replay = await pay(real_client)

    assert replay.status_code == 201
    assert replay.headers["X-Cache-Hit"] == "true"
    assert replay.content == first.content
    assert (await pay(real_client, "new-charge")).status_code == 502


@pytest.mark.parametrize("count", [-1, 101, 1.5, 1.0, "1", True, None])
async def test_invalid_failure_count_does_not_change_pending_failures(real_client, count):
    await real_client.post(CONTROL, json={"count": 1})
    invalid = await real_client.post(CONTROL, json={"count": count})

    assert invalid.status_code == 422
    assert (await pay(real_client)).status_code == 502
    assert (await pay(real_client)).status_code == 201


async def test_maximum_failure_count_is_accepted(real_client):
    response = await real_client.post(CONTROL, json={"count": 100})

    assert response.status_code == 200
    assert response.json() == {"failures_pending": 100}


async def test_disabled_simulation_route_is_absent(monkeypatch):
    monkeypatch.setenv("SIMULATION_CONTROLS_ENABLED", "false")
    monkeypatch.setenv("PROCESSING_DELAY_SECONDS", "0")
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.post(CONTROL, json={"count": 1})).status_code == 404
        assert CONTROL not in (await client.get("/openapi.json")).json()["paths"]
        assert (await pay(client)).status_code == 201


async def test_simulation_route_is_identified_in_docs(real_client):
    schema = (await real_client.get("/openapi.json")).json()
    operation = schema["paths"][CONTROL]["post"]

    assert operation["tags"] == ["Simulation"]
    assert "simulated processor" in operation["description"]


async def test_real_processor_reserves_failure_before_waiting(monkeypatch):
    processor = PaymentProcessor(delay_seconds=2)
    processor.fail_next(1)
    both_started = asyncio.Event()
    release = asyncio.Event()
    delays = []
    original_sleep = asyncio.sleep

    async def gated_sleep(delay):
        if delay != 2:
            return await original_sleep(delay)
        delays.append(delay)
        if len(delays) == 2:
            both_started.set()
        await release.wait()

    monkeypatch.setattr(asyncio, "sleep", gated_sleep)
    payment = PaymentRequest(**PAYMENT)
    charges = [asyncio.create_task(processor.charge(payment)) for _ in range(2)]
    try:
        async with asyncio.timeout(3):
            await both_started.wait()
            assert processor.failures_pending == 0
            assert all(not charge.done() for charge in charges)
            # Clearing future failures cannot change an already-started charge.
            processor.fail_next(0)
            release.set()
            results = await asyncio.gather(*charges, return_exceptions=True)

        assert delays == [2, 2]
        assert isinstance(results[0], PaymentProcessingError)
        assert results[1]["status"] == "success"
    finally:
        release.set()
        await asyncio.gather(*charges, return_exceptions=True)
