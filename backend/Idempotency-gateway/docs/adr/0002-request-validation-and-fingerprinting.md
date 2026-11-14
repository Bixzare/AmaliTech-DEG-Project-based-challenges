# ADR 0002: Request validation and body fingerprinting

- **Status:** Accepted
- **Date:** 2026-11-14

## Context

An idempotency key identifies one specific payment. The gateway has to tell apart three situations for a key it has seen before: a genuine retry (same body), a misuse of the key for a different payment (different body), and a request that was never valid in the first place. It also needs a way to decide whether two bodies are "the same" that does not depend on formatting.

## Decision

**Validate before touching the store.**

- The `Idempotency-Key` header is required, is stripped of surrounding whitespace, and must be 1 to 255 characters. Otherwise the gateway returns `400 Bad Request`.
- The body must contain `amount` (a decimal greater than 0 with at most two decimal places) and `currency` (three uppercase letters). Unknown fields are rejected. Invalid bodies return `422 Unprocessable Entity`.
- A request that fails validation never creates or consumes an idempotency record.

**Compare bodies by fingerprint.**

- The fingerprint is the SHA-256 digest of the validated payload serialised as canonical JSON: keys sorted, no insignificant whitespace, and the amount normalised to two decimal places.
- `{"amount": 100, "currency": "GHS"}`, the same object with its keys reordered, and the same object with `100.00` all produce the same fingerprint.
- The fingerprint is stored with the record. A later request with the same key and a different fingerprint returns `409 Conflict` with the message `Idempotency key already used for a different request body.`

**Status codes.**

- `201 Created` for a processed payment, and the same `201` when it is replayed.
- `409` rather than `422` for key reuse, so clients can distinguish "this body is malformed" from "this key belongs to another payment".

## Consequences

- A client that sends a malformed request can fix it and retry with the same key.
- Retries are not rejected because a client library serialised the JSON differently.
- Unknown fields are refused rather than ignored. If they were ignored, two bodies that differ only in an ignored field would share a fingerprint and be treated as the same payment.
- The store holds a fixed-size digest per key, not a copy of the request body.
