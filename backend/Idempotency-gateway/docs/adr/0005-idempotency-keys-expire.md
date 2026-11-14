# ADR 0005: Idempotency keys expire after 24 hours

- **Status:** Accepted
- **Date:** 2026-11-14

This is the "Developer's Choice" feature.

## Context

The challenge brief does not say how long a saved response should be kept. Keeping every record forever has two problems for a payment processor:

- **Unbounded growth.** Every payment adds a record that is never removed. In memory, that is a slow leak that ends in the process being killed; in a database, it is storage that grows with total lifetime volume.
- **No defined contract.** Clients cannot know how long a retry is safe, and the operator cannot reason about how much data the store holds.

Retries caused by timeouts happen within seconds or minutes of the original request, so the protection a record provides falls off quickly with age. How long to keep records is a tradeoff between storage and how late a retry is still protected.

## Decision

- A saved response is replayable for a fixed time to live, **24 hours by default**, configurable through `IDEMPOTENCY_TTL_SECONDS`. As precedent, Stripe documents that its idempotency keys can be removed once they are at least 24 hours old.
- The clock starts when the charge **completes**. In-flight records never expire.
- Expiry is enforced in two places:
  - **On read.** A lookup that finds an expired record deletes it and treats the key as new.
  - **By a background sweep.** A periodic task removes expired records, so keys that are never looked up again are still reclaimed. The interval is set by `IDEMPOTENCY_SWEEP_INTERVAL_SECONDS`.
- The store takes its clock as a parameter, so tests can advance time without sleeping.
- Records are stored under a `(client, key)` pair with a single default client for now. Scoping keys per client is a likely next step, and this keeps it a small change.

## Consequences

- Memory use is bounded by the number of payments in the last 24 hours, not by the total ever processed.
- The retry contract is explicit and can be documented for clients.
- **A retry that arrives after its key has expired is charged again.** This is the cost of the feature, and the reason the window is far longer than any realistic retry delay.
- A request that reuses an expired key with a different body is also processed as a new payment. Clients must not reuse keys across payments, which is already the rule.
- The TTL and sweep interval must be greater than zero. The gateway refuses to start otherwise, since a zero TTL would switch off replay protection.
- The sweep visits every record each run. That is fine at this scale; a store such as Redis would expire keys natively.
