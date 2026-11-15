# Test case: ADR 0003, concurrent requests share one charge task

Checks [ADR 0003](../docs/adr/0003-in-flight-requests-share-one-charge-task.md): a request that arrives while the same payment is still processing waits for it and receives its result, and a client disconnecting does not stop a charge that has started.

See [README.md](README.md) for how to send a request from the docs page. All steps use `POST /process-payment`.

## Setup for this case

The default 2-second processing time is too short to switch browser tabs in. Start the server with a 10-second delay for this case:

| Shell | Command |
|---|---|
| PowerShell | `$env:PROCESSING_DELAY_SECONDS = "10"; uvicorn app.main:app --port 8000` |
| Command Prompt | `set PROCESSING_DELAY_SECONDS=10 && uvicorn app.main:app --port 8000` |
| macOS or Linux | `PROCESSING_DELAY_SECONDS=10 uvicorn app.main:app --port 8000` |

Open <http://127.0.0.1:8000/docs> in **two browser tabs**, called tab A and tab B below. In each tab, expand `POST /process-payment` and click **Try it out**.

For each section, fill in the key and body in both tabs first, then click **Execute** in tab A and switch to tab B.

## 1. A duplicate that arrives mid-charge waits for the first request

Fill in both tabs with these values:

| Field | Value |
|---|---|
| idempotency-key | `adr3-order-1` |
| Request body | `{"amount": 100, "currency": "GHS"}` |

| Step | Action | Expected |
|---|---|---|
| 1.1 | Click **Execute** in tab A | Tab A shows a loading indicator |
| 1.2 | Within a few seconds, click **Execute** in tab B | Tab B also shows a loading indicator. It is not rejected and does not return early |
| 1.3 | Wait for both tabs | Both finish at the same moment, about 10 seconds after step 1.1 |
| 1.4 | Compare the two responses | Both are code `201` with the **same** `transaction_id`. Tab A has `x-cache-hit: false` and tab B has `x-cache-hit: true` |

One `transaction_id` across both tabs means one charge was made. Tab B waited for less than the full 10 seconds, because it joined a charge that was already running.

## 2. A different body under an in-flight key is rejected without waiting

| Step | Tab | Key | Body | Expected |
|---|---|---|---|---|
| 2.1 | A | `adr3-order-2` | `{"amount": 100, "currency": "GHS"}` | Click **Execute**. Tab A shows a loading indicator |
| 2.2 | B | `adr3-order-2` | `{"amount": 500, "currency": "GHS"}` | Click **Execute** while tab A is still loading. Code `409` immediately, detail `Idempotency key already used for a different request body.` |
| 2.3 | A | | | Tab A finishes normally with code `201` and `x-cache-hit: false` |

## 3. A client that disconnects does not lose the charge

This is the timeout-and-retry situation the gateway exists for. Fill in both tabs with these values:

| Field | Value |
|---|---|
| idempotency-key | `adr3-order-3` |
| Request body | `{"amount": 100, "currency": "GHS"}` |

| Step | Tab | Action | Expected |
|---|---|---|---|
| 3.1 | A | Click **Execute** | Tab A shows a loading indicator |
| 3.2 | A | After 2 or 3 seconds, **close tab A** | The client has gone away mid-charge |
| 3.3 | B | Click **Execute** | Tab B waits for the rest of the 10 seconds, counted from step 3.1, not a fresh 10 seconds |
| 3.4 | B | Read the response | Code `201` with `x-cache-hit: true` |
| 3.5 | B | Click **Execute** again | Code `201` immediately, the same `transaction_id`, `x-cache-hit: true` |

`x-cache-hit: true` in step 3.4 shows that tab B received the result of the charge tab A started. The charge carried on after tab A closed, and the retry did not start a second one.

Open the docs page in a new tab to replace tab A before the next section.

## 4. Different keys do not wait for each other

| Step | Tab | Key | Body | Expected |
|---|---|---|---|---|
| 4.1 | A | `adr3-order-4` | `{"amount": 100, "currency": "GHS"}` | Click **Execute** |
| 4.2 | B | `adr3-order-5` | `{"amount": 100, "currency": "GHS"}` | Click **Execute** straight away |
| 4.3 | both | | | Each finishes about 10 seconds after its own start, with different `transaction_id` values and `x-cache-hit: false` |

The two payments run side by side. Only requests with the same key share a charge.

## Afterwards

Stop the server and start it again without `PROCESSING_DELAY_SECONDS` to return to the default 2-second delay.

## Not covered by hand

Two behaviours from the ADR are checked by the automated tests in [tests/test_concurrency.py](../tests/test_concurrency.py) rather than here, because they cannot be triggered from a browser: cleaning up when the charge task itself is cancelled, and waiting for started charges during shutdown.
