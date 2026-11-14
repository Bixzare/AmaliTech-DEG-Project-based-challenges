"""Process-local coordination and storage of payment responses."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


class IdempotencyKeyConflict(Exception):
    """The key is already reserved for a different validated payment body."""


@dataclass(frozen=True)
class StoredResponse:
    status_code: int
    body: dict[str, str]


@dataclass
class _Entry:
    fingerprint: str
    task: asyncio.Task[StoredResponse] | None = None
    response: StoredResponse | None = None


class IdempotencyStore:
    def __init__(
        self, ttl_seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._entries: dict[tuple[str, str], _Entry] = {}

    async def execute(
        self,
        scope: tuple[str, str],
        fingerprint: str,
        work: Callable[[], Awaitable[StoredResponse]],
    ) -> tuple[StoredResponse, bool]:
        """Return (response, replayed), sharing one charge task for each key."""
        # Atomic check-and-register: no await between lookup and registration.
        # All callers use one event loop, so another request cannot claim this key.
        entry = self._entries.get(scope)
        if entry is not None:
            if entry.fingerprint != fingerprint:
                raise IdempotencyKeyConflict(
                    "Idempotency key already used for a different request body."
                )
            if entry.response is not None:
                return entry.response, True
            assert entry.task is not None
            return await asyncio.shield(entry.task), True

        entry = _Entry(fingerprint=fingerprint)
        self._entries[scope] = entry
        task = asyncio.create_task(self._run(scope, entry, work))
        entry.task = task
        task.add_done_callback(lambda finished: self._task_done(scope, entry, finished))
        # The charge owns its task; even the first caller only waits through a
        # shield. Cancelling a request must not cancel the shared charge.
        return await asyncio.shield(task), False

    async def _run(
        self,
        scope: tuple[str, str],
        entry: _Entry,
        work: Callable[[], Awaitable[StoredResponse]],
    ) -> StoredResponse:
        try:
            response = await work()
            entry.response = response
            return response
        except BaseException:
            # Includes cancellation of the charge itself, not a shielded waiter.
            if self._entries.get(scope) is entry:
                del self._entries[scope]
            raise

    def _task_done(
        self, scope: tuple[str, str], entry: _Entry, task: asyncio.Task[StoredResponse]
    ) -> None:
        if task.cancelled():
            # Cancellation before _run starts cannot execute its cleanup block.
            if self._entries.get(scope) is entry:
                del self._entries[scope]
            return
        # Retrieve failures even when every requesting client has disconnected.
        task.exception()

    async def drain(self) -> None:
        """Wait for charges already started before application shutdown."""
        tasks = [
            entry.task
            for entry in self._entries.values()
            if entry.task is not None and not entry.task.done()
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
