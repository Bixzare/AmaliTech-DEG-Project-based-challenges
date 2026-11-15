# Test case: ADR 0001, FastAPI with an in-memory store

Checks [ADR 0001](../docs/adr/0001-fastapi-and-in-memory-store.md): the service runs as a single FastAPI process with no external services, and its idempotency records live in that process's memory.

See [README.md](README.md) for how to send a request from the docs page.

## 1. The server starts and serves its docs

| Step | Action | Expected |
|---|---|---|
| 1.1 | Start the server with `uvicorn app.main:app --port 8000` | The terminal shows `Application startup complete` and no errors |
| 1.2 | Open <http://127.0.0.1:8000/health> | `{"status":"ok"}` |
| 1.3 | Open <http://127.0.0.1:8000/docs> | The docs page lists `GET /health` and `POST /process-payment` |

## 2. A payment is processed and remembered

Use these values:

| Field | Value |
|---|---|
| idempotency-key | `adr1-order-1` |
| Request body | `{"amount": 100, "currency": "GHS"}` |

| Step | Action | Expected |
|---|---|---|
| 2.1 | Send `POST /process-payment` with the values above | Code `201` after about 2 seconds, message `Charged 100 GHS`, header `x-cache-hit: false` |
| 2.2 | Note the `transaction_id` in the response | |
| 2.3 | Click **Execute** again without changing anything | Code `201` immediately, the same `transaction_id`, header `x-cache-hit: true` |

## 3. Records are held in memory only

This step shows the limit the ADR accepts: records do not survive a restart.

| Step | Action | Expected |
|---|---|---|
| 3.1 | Stop the server with `Ctrl+C` and start it again | The server starts cleanly |
| 3.2 | Reload the docs page and send the request from step 2.1 again, with the same key and body | Code `201` after about 2 seconds, a **different** `transaction_id`, header `x-cache-hit: false` |

The key from before the restart is treated as new, because the store was emptied when the process stopped.

## 4. Invalid configuration stops the server from starting

| Step | Action | Expected |
|---|---|---|
| 4.1 | Stop the server. Set `IDEMPOTENCY_TTL_SECONDS` to `0` and start it again | The server refuses to start, with an error naming `IDEMPOTENCY_TTL_SECONDS` |
| 4.2 | Remove the variable and start the server again | The server starts cleanly |

Setting and removing the variable:

| Shell | Set | Remove |
|---|---|---|
| PowerShell | `$env:IDEMPOTENCY_TTL_SECONDS = "0"` | `Remove-Item Env:IDEMPOTENCY_TTL_SECONDS` |
| Command Prompt | `set IDEMPOTENCY_TTL_SECONDS=0` | `set IDEMPOTENCY_TTL_SECONDS=` |
| macOS or Linux | `export IDEMPOTENCY_TTL_SECONDS=0` | `unset IDEMPOTENCY_TTL_SECONDS` |
