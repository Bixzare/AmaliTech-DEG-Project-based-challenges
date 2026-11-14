import asyncio
import gc

import pytest

from app.schemas import PaymentRequest
from app.store import StoredResponse

pytestmark = pytest.mark.anyio

PAYMENT = {"amount": 100, "currency": "GHS"}
SCOPE = ("default", "concurrent-payment")


def observe_arrivals(monkeypatch, store, expected):
    """Signal when requests have entered execute, without relying on delays."""
    arrived = asyncio.Event()
    execute = store.execute
    count = 0

    async def observed(*args, **kwargs):
        nonlocal count
        count += 1
        if count == expected:
            arrived.set()
        return await execute(*args, **kwargs)

    monkeypatch.setattr(store, "execute", observed)
    return arrived


def payment_work(processor):
    async def work():
        return StoredResponse(201, await processor.charge(PaymentRequest(**PAYMENT)))

    return work


async def test_five_requests_share_one_charge(client, app, processor, monkeypatch):
    processor.gated = True
    arrived = observe_arrivals(monkeypatch, app.state.store, expected=5)
    requests = []
    try:
        async with asyncio.timeout(3):
            requests.append(asyncio.create_task(client.post(
                "/process-payment", headers={"Idempotency-Key": SCOPE[1]}, json=PAYMENT
            )))
            await processor.started.wait()
            requests.extend(asyncio.create_task(client.post(
                "/process-payment", headers={"Idempotency-Key": SCOPE[1]}, json=PAYMENT
            )) for _ in range(4))
            await arrived.wait()

            assert all(not request.done() for request in requests)
            assert processor.calls == 1
            processor.release.set()
            responses = await asyncio.gather(*requests)

        assert all(response.status_code == 201 for response in responses)
        assert all(response.content == responses[0].content for response in responses)
        assert [response.headers["X-Cache-Hit"] for response in responses].count("false") == 1
        assert [response.headers["X-Cache-Hit"] for response in responses].count("true") == 4
        assert processor.calls == 1
    finally:
        processor.release.set()
        await asyncio.gather(*requests, return_exceptions=True)


@pytest.mark.parametrize("changed", [dict(amount=500, currency="GHS"), dict(amount=100, currency="USD")])
async def test_in_flight_mismatch_conflicts_before_charge_finishes(client, processor, changed):
    processor.gated = True
    first = asyncio.create_task(client.post(
        "/process-payment", headers={"Idempotency-Key": SCOPE[1]}, json=PAYMENT
    ))
    try:
        async with asyncio.timeout(3):
            await processor.started.wait()
            conflict = await client.post(
                "/process-payment", headers={"Idempotency-Key": SCOPE[1]}, json=changed
            )
            assert conflict.status_code == 409
            assert conflict.json() == {
                "detail": "Idempotency key already used for a different request body."
            }
            assert "X-Cache-Hit" not in conflict.headers
            assert not first.done()
            assert not processor.release.is_set()
            assert processor.calls == 1
            processor.release.set()
            assert (await first).status_code == 201
    finally:
        processor.release.set()
        await asyncio.gather(first, return_exceptions=True)


async def test_cancelling_first_waiter_preserves_charge(app, processor):
    processor.gated = True
    store = app.state.store
    work = payment_work(processor)
    first = asyncio.create_task(store.execute(SCOPE, "fingerprint", work))
    try:
        async with asyncio.timeout(3):
            await processor.started.wait()
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first

            charge_task = processor.charge_tasks[0]
            assert not charge_task.done()
            processor.release.set()
            saved = await charge_task
            replay, replayed = await store.execute(SCOPE, "fingerprint", work)

            assert replay == saved
            assert replayed is True
            assert processor.calls == 1
    finally:
        processor.release.set()
        await asyncio.gather(first, *processor.charge_tasks, return_exceptions=True)


async def test_cancelling_charge_releases_key_without_callback_errors(app, processor):
    processor.gated = True
    store = app.state.store
    work = payment_work(processor)
    loop = asyncio.get_running_loop()
    errors = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda loop, context: errors.append(context))
    first = asyncio.create_task(store.execute(SCOPE, "fingerprint", work))
    try:
        async with asyncio.timeout(3):
            await processor.started.wait()
            processor.charge_tasks[0].cancel()
            with pytest.raises(asyncio.CancelledError):
                await first

            processor.release.set()
            response, replayed = await store.execute(SCOPE, "fingerprint", work)
            assert response.status_code == 201
            assert replayed is False
            assert processor.calls == 2
            await asyncio.sleep(0)  # Let task completion callbacks run.
            assert errors == []
    finally:
        processor.release.set()
        await asyncio.gather(first, *processor.charge_tasks, return_exceptions=True)
        loop.set_exception_handler(previous_handler)


async def test_charge_cancelled_before_start_does_not_leave_key_reserved(app, processor, monkeypatch):
    create_task = asyncio.create_task

    def cancel_before_start(coroutine):
        task = create_task(coroutine)
        task.cancel()
        return task

    work = payment_work(processor)
    async with asyncio.timeout(3):
        with monkeypatch.context() as patch:
            patch.setattr(asyncio, "create_task", cancel_before_start)
            with pytest.raises(asyncio.CancelledError):
                await app.state.store.execute(SCOPE, "fingerprint", work)

        assert processor.calls == 0
        response, replayed = await app.state.store.execute(SCOPE, "fingerprint", work)
        assert response.status_code == 201
        assert replayed is False
        assert processor.calls == 1


async def test_different_keys_can_process_concurrently(client, processor):
    processor.gated = True
    requests = []
    try:
        async with asyncio.timeout(3):
            requests.append(asyncio.create_task(client.post(
                "/process-payment", headers={"Idempotency-Key": "independent-a"}, json=PAYMENT
            )))
            await processor.started.wait()
            processor.started.clear()
            requests.append(asyncio.create_task(client.post(
                "/process-payment", headers={"Idempotency-Key": "independent-b"}, json=PAYMENT
            )))
            await processor.started.wait()
            assert processor.calls == 2
            assert all(not request.done() for request in requests)
            processor.release.set()
            responses = await asyncio.gather(*requests)

        assert all(response.status_code == 201 for response in responses)
        assert all(response.headers["X-Cache-Hit"] == "false" for response in responses)
        assert responses[0].json()["transaction_id"] != responses[1].json()["transaction_id"]
    finally:
        processor.release.set()
        await asyncio.gather(*requests, return_exceptions=True)


async def test_unobserved_charge_failure_is_retrieved(app, processor):
    processor.gated = True
    processor.fail = True
    store = app.state.store
    loop = asyncio.get_running_loop()
    errors = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda loop, context: errors.append(context))
    first = asyncio.create_task(store.execute(SCOPE, "fingerprint", payment_work(processor)))
    try:
        async with asyncio.timeout(3):
            await processor.started.wait()
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            finished = asyncio.Event()
            processor.charge_tasks[0].add_done_callback(lambda task: finished.set())
            processor.release.set()
            await finished.wait()
            # Drop the spy's task reference without retrieving its exception.
            processor.charge_tasks.clear()
            gc.collect()
            await asyncio.sleep(0)
            assert errors == []
    finally:
        processor.release.set()
        loop.set_exception_handler(previous_handler)


async def test_shutdown_drains_charge_after_request_is_cancelled(app, processor):
    processor.gated = True
    work = payment_work(processor)
    entered = asyncio.Event()
    exit_requested = asyncio.Event()
    exiting = asyncio.Event()

    async def lifecycle():
        async with app.router.lifespan_context(app):
            entered.set()
            await exit_requested.wait()
            exiting.set()

    lifetime = asyncio.create_task(lifecycle())
    first = None
    try:
        async with asyncio.timeout(3):
            await entered.wait()
            first = asyncio.create_task(app.state.store.execute(SCOPE, "fingerprint", work))
            await processor.started.wait()
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            exit_requested.set()
            await exiting.wait()
            assert not lifetime.done()
            assert not processor.charge_tasks[0].done()

            processor.release.set()
            await lifetime
            response, replayed = await app.state.store.execute(SCOPE, "fingerprint", work)
            assert response.status_code == 201
            assert replayed is True
            assert processor.calls == 1
    finally:
        processor.release.set()
        exit_requested.set()
        await asyncio.gather(lifetime, *([first] if first else []), return_exceptions=True)
