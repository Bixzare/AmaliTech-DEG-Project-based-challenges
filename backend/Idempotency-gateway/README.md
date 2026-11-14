# Idempotency Gateway

## Overview

This API simulates payment processing and is designed to let clients retry requests safely using an `Idempotency-Key`. It uses FastAPI and an in-memory store in a single worker process to save and replay payment responses.

The diagram describes the target design. Implementation is being added in tested increments; the ADRs record the decisions and their limits.

## Architecture diagram
```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant G as Gateway (FastAPI)
    participant S as Idempotency Store
    participant P as Payment Processor

    C->>G: POST /process-payment with Idempotency-Key and JSON body
    G->>G: Validate key and body
    alt Key missing or invalid
        G-->>C: 400 Bad Request
    else Body invalid
        G-->>C: 422 Unprocessable Entity
    else Request valid
        G->>S: Look up key and compare body fingerprint
        alt Key unknown or expired
            S->>P: Start charge task and mark key in flight
            P-->>S: Charge result
            alt Charge succeeded
                S->>S: Save response and start TTL
                S-->>G: Response
                G-->>C: 201 Created, X-Cache-Hit false
            else Charge failed
                S->>S: Release key
                S-->>G: Error
                G-->>C: 502 Bad Gateway, safe to retry
            end
        else Key known with a different body
            S-->>G: Conflict
            G-->>C: 409 Conflict
        else Key known, same body, still in flight
            Note over G,S: Wait on the running charge task. No second charge starts.
            S-->>G: Result of the first request
            G-->>C: 201 Created, X-Cache-Hit true
        else Key known, same body, completed
            S-->>G: Saved response
            G-->>C: 201 Created, X-Cache-Hit true
        end
    end
```

## Design decisions

- [ADR 0001: FastAPI with an in-memory store](docs/adr/0001-fastapi-and-in-memory-store.md)
- [ADR 0002: Request validation and fingerprinting](docs/adr/0002-request-validation-and-fingerprinting.md)
- [ADR 0003: Concurrent requests share one charge task](docs/adr/0003-in-flight-requests-share-one-charge-task.md)
- [ADR 0004: Failed charges release their key](docs/adr/0004-failed-charges-release-the-key.md)

## Developer's choice

[ADR 0005: Idempotency keys expire](docs/adr/0005-idempotency-keys-expire.md) defines a configurable retention window and periodic cleanup. Retrying after expiry creates a new payment; records are also lost on process restart.
