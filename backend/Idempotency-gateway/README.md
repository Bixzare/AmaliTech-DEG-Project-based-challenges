# Idempotency Gateway

## Overview

This API simulates payment processing and is designed to let clients retry requests safely using an `Idempotency-Key`. It uses FastAPI and an in-memory store in a single worker process to save and replay payment responses.

The diagram describes the request flow; the ADRs record the decisions and their limits.

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

## Setup

Install Git and Python 3.11 or newer. No database or external service is required.

Clone the repository if you do not already have it:

```text
git clone https://github.com/Bixzare/AmaliTech-DEG-Project-based-challenges.git
```

Start the following commands from the repository root (`AmaliTech-DEG-Project-based-challenges`). If your terminal is already inside `backend/Idempotency-gateway`, skip the first `cd` command. Create the virtual environment once; on later visits, activate it and start the server.

### Windows Command Prompt (CMD)

```bat
cd backend\Idempotency-gateway
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

### Windows PowerShell

```powershell
cd backend\Idempotency-gateway
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

If PowerShell blocks the activation script, use the virtual environment's interpreter directly from the project folder:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Confirm that `python --version` reports Python 3.11 or newer before creating the environment.

### macOS or Linux

```bash
cd backend/Idempotency-gateway
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

Confirm that `python3 --version` reports Python 3.11 or newer before creating the environment.

### Check the running server

Open [the health endpoint](http://127.0.0.1:8000/health); it should return `{"status":"ok"}`. Open [the interactive API documentation](http://127.0.0.1:8000/docs) to send payment requests. Stop the server with `Ctrl+C`.

Run one worker process. The in-memory store is not shared across workers, and restarting the server clears its records.

### Run the tests

Stop the server, or open another terminal in the project folder and activate the same virtual environment. Then run:

```text
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

On Windows, activation is optional if you use the explicit interpreter path:

```text
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
```

### Configuration

Set environment variables before starting the server. Invalid settings prevent startup and report the variable that needs correction.

| Environment variable | Default | Rule | Purpose |
|---|---|---|---|
| `PROCESSING_DELAY_SECONDS` | `2.0` | Finite, at least zero | Simulated payment processing delay |
| `IDEMPOTENCY_TTL_SECONDS` | `86400` | Finite, greater than zero | Retention window for completed responses |
| `IDEMPOTENCY_SWEEP_INTERVAL_SECONDS` | `60` | Finite, greater than zero | Interval between expiry sweeps |
| `SIMULATION_CONTROLS_ENABLED` | `true` | `true`, `false`, `1` or `0` (case-insensitive) | Enable the manual failure-control endpoint |

The TTL starts when a charge succeeds. Replaying a response does not extend its expiry, and in-flight charges never expire. Expired entries are removed on lookup and by the background sweeper. A retry at or after expiry starts a new charge, even with the same key and body.

To try a failed payment without restarting the server, open `/docs` and send `{"count": 1}` to `POST /simulation/fail-next-charges` under **Simulation**. The next new charge waits for the configured processing delay and returns `502`. Retry the same payment with the same key to receive `201`; the failed attempt did not consume the key. The count can be an integer from 0 to 100, replaces the pending count, and zero clears it. Set `SIMULATION_CONTROLS_ENABLED=false` before starting the server to remove this route entirely. This control is only for the simulated processor.

## Design decisions

- [ADR 0001: FastAPI with an in-memory store](docs/adr/0001-fastapi-and-in-memory-store.md)
- [ADR 0002: Request validation and fingerprinting](docs/adr/0002-request-validation-and-fingerprinting.md)
- [ADR 0003: Concurrent requests share one charge task](docs/adr/0003-in-flight-requests-share-one-charge-task.md)
- [ADR 0004: Failed charges release their key](docs/adr/0004-failed-charges-release-the-key.md)

Started charges run in their own tasks. Requests for the same key and payment wait for that task through cancellation shielding, so cancelling one request does not cancel the charge. During normal shutdown, the application stops and awaits the background sweeper, then waits for started charges to finish. This does not protect against the process being killed or records being lost on restart.

## Developer's choice

[ADR 0005: Idempotency keys expire](docs/adr/0005-idempotency-keys-expire.md) defines a configurable retention window and periodic cleanup. Retrying after expiry creates a new payment; records are also lost on process restart.
