import asyncio

import pytest

from app.config import Settings
from app.main import create_app

pytestmark = pytest.mark.anyio
PAYMENT = {"amount": 100, "currency": "GHS"}


@pytest.fixture
def app(processor, fake_clock):
    return create_app(
        settings=Settings(
            processing_delay_seconds=0,
            idempotency_ttl_seconds=10,
            idempotency_sweep_interval_seconds=0.01,
        ),
        processor=processor,
        clock=fake_clock,
    )


async def pay(client, key="expiring-payment", body=None):
    return await client.post(
        "/process-payment",
        headers={"Idempotency-Key": key},
        json=PAYMENT if body is None else body,
    )


@pytest.mark.parametrize("expiry_time", [10, 10.1])
async def test_replay_before_expiry_then_new_charge(client, fake_clock, processor, expiry_time):
    first = await pay(client)
    fake_clock.advance(9.9)
    replay = await pay(client)

    assert first.status_code == replay.status_code == 201
    assert replay.headers["X-Cache-Hit"] == "true"
    assert replay.content == first.content
    assert processor.calls == 1

    fake_clock.advance(expiry_time - fake_clock())
    new = await pay(client)

    assert new.status_code == 201
    assert new.headers["X-Cache-Hit"] == "false"
    assert new.json()["transaction_id"] != first.json()["transaction_id"]
    assert processor.calls == 2


@pytest.mark.parametrize(
    "body", [{"amount": 500, "currency": "GHS"}, {"amount": 100, "currency": "USD"}]
)
async def test_expired_key_accepts_different_body(client, fake_clock, processor, body):
    first = await pay(client)
    fake_clock.advance(10)
    new = await pay(client, body=body)

    assert first.status_code == new.status_code == 201
    assert new.headers["X-Cache-Hit"] == "false"
    assert new.json()["transaction_id"] != first.json()["transaction_id"]
    assert new.json()["message"] == f"Charged {body['amount']} {body['currency']}"
    assert processor.calls == 2


async def test_in_flight_key_survives_time_and_ttl_starts_on_completion(
    client, app, fake_clock, processor, monkeypatch
):
    processor.gated = True
    duplicate_arrived = asyncio.Event()
    execute = app.state.store.execute
    arrivals = 0

    async def observed(*args, **kwargs):
        nonlocal arrivals
        arrivals += 1
        if arrivals == 2:
            duplicate_arrived.set()
        return await execute(*args, **kwargs)

    monkeypatch.setattr(app.state.store, "execute", observed)
    requests = [asyncio.create_task(pay(client))]
    try:
        async with asyncio.timeout(3):
            await processor.started.wait()
            fake_clock.advance(100)
            assert app.state.store.purge_expired() == 0
            requests.append(asyncio.create_task(pay(client)))
            await duplicate_arrived.wait()
            assert all(not request.done() for request in requests)
            assert processor.calls == 1
            conflict = await pay(client, body={"amount": 500, "currency": "GHS"})
            assert conflict.status_code == 409

            processor.release.set()
            first, duplicate = await asyncio.gather(*requests)
            assert first.status_code == duplicate.status_code == 201
            assert first.content == duplicate.content
            assert duplicate.headers["X-Cache-Hit"] == "true"

            fake_clock.advance(9)
            replay = await pay(client)
            assert replay.content == first.content
            assert replay.headers["X-Cache-Hit"] == "true"
            assert processor.calls == 1
            fake_clock.advance(1)
            new = await pay(client)
            assert new.headers["X-Cache-Hit"] == "false"
            assert new.json()["transaction_id"] != first.json()["transaction_id"]
            assert processor.calls == 2
    finally:
        processor.release.set()
        await asyncio.gather(*requests, return_exceptions=True)


async def test_purge_removes_only_expired_completed_entries(client, app, fake_clock, processor):
    await pay(client, key="expired")
    fake_clock.advance(6)
    live = await pay(client, key="live")
    processor.gated = True
    processor.started.clear()
    in_flight = asyncio.create_task(pay(client, key="in-flight"))
    try:
        async with asyncio.timeout(3):
            await processor.started.wait()
            fake_clock.advance(4)
            assert app.state.store.purge_expired() == 1
            assert set(app.state.store._entries) == {("default", "live"), ("default", "in-flight")}
            assert app.state.store.purge_expired() == 0
            assert not in_flight.done()
            replay = await pay(client, key="live")
            assert replay.content == live.content
            assert replay.headers["X-Cache-Hit"] == "true"
            assert processor.calls == 3
            processor.release.set()
            assert (await in_flight).status_code == 201
    finally:
        processor.release.set()
        await asyncio.gather(in_flight, return_exceptions=True)


async def test_lifespan_sweeps_without_a_lookup_and_stops_on_exit(client, app, fake_clock):
    async with app.router.lifespan_context(app):
        sweeper = app.state.sweeper_task
        await pay(client)
        assert len(app.state.store._entries) == 1
        fake_clock.advance(10)
        async with asyncio.timeout(3):
            while app.state.store._entries:
                await asyncio.sleep(0.01)
        assert not sweeper.done()

    assert sweeper.done()
    assert sweeper.cancelled()


async def test_shutdown_stops_sweeper_before_draining_charge(client, app, processor, monkeypatch):
    processor.gated = True
    draining = asyncio.Event()
    entered = asyncio.Event()
    exit_requested = asyncio.Event()
    original_drain = app.state.store.drain

    async def observed_drain():
        assert app.state.sweeper_task.done()
        draining.set()
        await original_drain()

    monkeypatch.setattr(app.state.store, "drain", observed_drain)

    async def lifecycle():
        async with app.router.lifespan_context(app):
            entered.set()
            await exit_requested.wait()

    lifetime = asyncio.create_task(lifecycle())
    payment = None
    try:
        async with asyncio.timeout(3):
            await entered.wait()
            payment = asyncio.create_task(pay(client))
            await processor.started.wait()
            payment.cancel()
            with pytest.raises(asyncio.CancelledError):
                await payment
            exit_requested.set()
            await draining.wait()
            assert not lifetime.done()
            assert not processor.charge_tasks[0].done()
            processor.release.set()
            await lifetime
            assert processor.charge_tasks[0].done()
            assert not processor.charge_tasks[0].cancelled()
    finally:
        processor.release.set()
        exit_requested.set()
        await asyncio.gather(lifetime, *([payment] if payment else []), return_exceptions=True)
