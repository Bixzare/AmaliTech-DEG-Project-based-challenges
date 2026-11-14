# ADR 0001: FastAPI with an in-memory idempotency store

- **Status:** Accepted
- **Date:** 2026-11-14

## Context

The gateway exposes one payment endpoint and must guarantee that a payment with a given `Idempotency-Key` is processed exactly once. Two constraints shape the choice of stack:

- A duplicate request that arrives while the first is still processing has to wait for it and return its result. That is a concurrency problem, so the framework's concurrency model matters.
- A reviewer should be able to clone the repository and start the server with one command, with no external services to install.

## Decision

- Build the API with **FastAPI** on **uvicorn**. Requests are handled as coroutines on a single event loop, which makes "wait for another request's result" a plain `await` and gives a simple way to make the key check atomic (see ADR 0003). FastAPI also validates request bodies and publishes OpenAPI docs at `/docs` without extra work.
- Keep idempotency records in an **in-memory dictionary**, owned by one `IdempotencyStore` class. No other module reads or writes the dictionary directly.
- Run as a **single process**.

## Consequences

- Setup is a virtual environment, two runtime dependencies and one command.
- Records are lost when the process restarts, so a retry that arrives after a restart would be charged again.
- The guarantee holds only within one worker process. Running several workers or instances would give each its own store.
- For production, the store would move to a shared database such as Redis, using an atomic set-if-absent with an expiry to claim a key. Because all access goes through `IdempotencyStore`, that change is contained to one class.
