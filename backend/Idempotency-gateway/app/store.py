"""Process-local storage for completed payment responses."""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


class IdempotencyKeyConflict(Exception):
    """The key is already reserved for a different validated payment body."""


@dataclass(frozen=True)
class StoredResponse:
    status_code: int
    body: dict[str, str]


@dataclass(frozen=True)
class _Entry:
    fingerprint: str
    response: StoredResponse


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
        """Return (response, replayed) for a completed payment or new work.

        In-flight coordination and expiry are added in subsequent implementation
        steps; this checkpoint covers sequential replay and conflicts.
        """
        entry = self._entries.get(scope)
        if entry is not None:
            if entry.fingerprint != fingerprint:
                raise IdempotencyKeyConflict(
                    "Idempotency key already used for a different request body."
                )
            return entry.response, True

        response = await work()
        self._entries[scope] = _Entry(fingerprint=fingerprint, response=response)
        return response, False
