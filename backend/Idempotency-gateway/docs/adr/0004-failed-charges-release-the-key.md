# ADR 0004: A failed charge releases its key

- **Status:** Accepted
- **Date:** 2026-11-14

## Context

The payment processor can fail. The gateway has to decide what a failure means for the idempotency key: either the failure is saved and replayed like any other response, or the key is freed so the payment can be attempted again.

Clients retry precisely because something went wrong. If a failure were saved, every retry with that key would receive the same error for as long as the record lived, and the client would have to invent a new key to try again. New keys for the same payment are how double charges happen.

## Decision

- Only **successful** charges are saved and replayed.
- If the processor fails, the store deletes the in-flight record and nothing is cached.
- The request that started the charge, and any requests waiting on it, receive `502 Bad Gateway` with a message stating that no charge was made and that the request can be retried with the same key.
- The next request with that key is treated as a first request and starts a new charge.

## Consequences

- Clients keep one key per payment for its whole life, through failures and retries.
- A failure is reported once per attempt rather than replayed.
- This is safe because the simulated processor fails without moving money. A real processor can fail ambiguously, for example by timing out after the charge went through. Handling that would mean keeping the key locked and reconciling with the processor before allowing a retry, which is out of scope here.
