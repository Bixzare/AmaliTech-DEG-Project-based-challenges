# ADR 0003: Concurrent requests share one charge task

- **Status:** Accepted
- **Date:** 2026-11-14

## Context

Processing a payment takes about two seconds. Two things can happen in that window:

- A second request with the same key arrives before the first has finished. If both check the store, both see no completed record, and both charge the customer.
- The first client gives up waiting and disconnects, then retries. This is the timeout scenario that causes double charging today. If the charge is tied to the first request, cancelling that request could abandon the charge halfway.

The second request must not start a new charge and must not be rejected. It should wait and receive the first request's result.

## Decision

- When a key is seen for the first time, the store starts the charge as its **own background task** and records the key as in flight, holding a reference to that task.
- **Every request waits on the task, including the first.** A request for an in-flight key awaits the same task and returns its result with `X-Cache-Hit: true`.
- Waiting is shielded, so a client disconnecting cancels only that client's wait. The charge task runs to completion and saves its result for the retry.
- **The check and the registration are atomic.** The store looks up the key and inserts the in-flight record without yielding to the event loop in between. Since the event loop runs one coroutine at a time, no other request can run between those two steps, so two requests can never both register the same key. No lock is needed.
- A request for an in-flight key with a different body fingerprint returns `409` straight away, without waiting.

## Consequences

- One code path serves the first request, concurrent duplicates and later replays.
- A charge that has started always finishes and is recorded, whether or not anyone is still waiting for it.
- Waiters hold an open connection for up to the processing time. That is acceptable here because the processing time is short and bounded.
- The atomicity argument relies on a single event loop in a single process. With multiple workers the same guarantee would come from an atomic operation in a shared store (see ADR 0001).
