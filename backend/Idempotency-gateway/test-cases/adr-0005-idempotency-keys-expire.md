# Test case: ADR 0005, idempotency keys expire

Checks [ADR 0005](../docs/adr/0005-idempotency-keys-expire.md): a saved response can be replayed for a fixed time after the charge completes, and after that the key is treated as new.

See [README.md](README.md) for how to send a request from the docs page. All steps use `POST /process-payment` in one browser tab.

## Setup for this case

The default retention time is 24 hours. Start the server with a 30-second retention time for this case:

| Shell | Command |
|---|---|
| PowerShell | `$env:IDEMPOTENCY_TTL_SECONDS = "30"; uvicorn app.main:app --port 8000` |
| Command Prompt | `set IDEMPOTENCY_TTL_SECONDS=30 && uvicorn app.main:app --port 8000` |
| macOS or Linux | `IDEMPOTENCY_TTL_SECONDS=30 uvicorn app.main:app --port 8000` |

The steps are timed, so keep a clock or stopwatch in view. Each response also carries a `processed_at` time, which is when its charge completed and its 30 seconds began.

## 1. A response replays until it expires, then the key is new again

Use these values for every step:

| Field | Value |
|---|---|
| idempotency-key | `adr5-order-1` |
| Request body | `{"amount": 100, "currency": "GHS"}` |

| Step | When | Action | Expected |
|---|---|---|---|
| 1.1 | Start the stopwatch | Click **Execute** | Code `201` after about 2 seconds, header `x-cache-hit: false`. Note the `transaction_id` |
| 1.2 | Straight away | Click **Execute** | Code `201` immediately, the same `transaction_id`, header `x-cache-hit: true` |
| 1.3 | At about 20 seconds | Click **Execute** | Same as step 1.2. The response is still within its 30 seconds |
| 1.4 | At about 40 seconds | Click **Execute** | Code `201` after about 2 seconds, a **different** `transaction_id`, header `x-cache-hit: false` |

Step 1.4 is a new charge: the saved response expired, so the key was treated as never seen. This is the cost of expiry that the ADR accepts, and the reason the real default is 24 hours.

Step 1.4 also shows that replaying does not extend the retention time. It came only 20 seconds after the replay in step 1.3, but more than 30 seconds after the charge completed in step 1.1.

## 2. An expired key can be used for a different payment

| Step | When | Key | Body | Expected |
|---|---|---|---|---|
| 2.1 | Restart the stopwatch | `adr5-order-2` | `{"amount": 100, "currency": "GHS"}` | Code `201`, message `Charged 100 GHS`, header `x-cache-hit: false` |
| 2.2 | Straight away | `adr5-order-2` | `{"amount": 500, "currency": "GHS"}` | Code `409`, detail `Idempotency key already used for a different request body.` |
| 2.3 | At about 40 seconds | `adr5-order-2` | `{"amount": 500, "currency": "GHS"}` | Code `201` after about 2 seconds, message `Charged 500 GHS`, header `x-cache-hit: false` |

The request that was rejected in step 2.2 is accepted in step 2.3, because the record it conflicted with has expired.

## Afterwards

Stop the server and start it again without `IDEMPOTENCY_TTL_SECONDS` to return to the 24-hour default.

## Not covered by hand

Three behaviours from the ADR are checked by the automated tests in [tests/test_expiry.py](../tests/test_expiry.py) rather than here:

- **The background sweep.** It removes expired records that nobody looks up again. From outside, a swept record and one that expired on lookup look the same, so there is nothing to observe in the docs page.
- **In-flight charges never expire.** Showing this would need a charge that runs for longer than the retention time.
- **The exact expiry boundary.** The tests use a controllable clock to check the moment of expiry precisely.

The refusal to start with a retention time of zero is covered in the [ADR 0001 test case](adr-0001-fastapi-and-in-memory-store.md#4-invalid-configuration-stops-the-server-from-starting).
