# Test case: ADR 0004, a failed charge releases its key

Checks [ADR 0004](../docs/adr/0004-failed-charges-release-the-key.md): when the payment processor fails, nothing is saved, the client is told no charge was made, and the same key can be retried.

See [README.md](README.md) for how to send a request from the docs page.

## How failures are triggered

The simulated processor never fails by itself. The docs page has a second endpoint for this, under the **Simulation** heading: `POST /simulation/fail-next-charges`. Sending it `{"count": 1}` makes the next charge fail. It responds with `{"failures_pending": 1}`.

A failing charge still takes the full processing time before it fails.

Sections 1 to 3 use the default 2-second delay and one browser tab.

## 1. A failed charge can be retried with the same key

| Step | Endpoint | Key | Body | Expected |
|---|---|---|---|---|
| 1.1 | `/simulation/fail-next-charges` | | `{"count": 1}` | Code `200`, `{"failures_pending": 1}` |
| 1.2 | `/process-payment` | `adr4-order-1` | `{"amount": 100, "currency": "GHS"}` | Code `502` after about 2 seconds, detail `Payment processing failed. No charge was made; retry with the same Idempotency-Key.`, no `x-cache-hit` header |
| 1.3 | `/process-payment` | `adr4-order-1` | `{"amount": 100, "currency": "GHS"}` | Code `201` after about 2 seconds, header `x-cache-hit: false`. Note the `transaction_id` |
| 1.4 | `/process-payment` | `adr4-order-1` | `{"amount": 100, "currency": "GHS"}` | Code `201` immediately, the same `transaction_id`, header `x-cache-hit: true` |

Step 1.3 is the point of this case. It took the full 2 seconds and returned `x-cache-hit: false`, so it was processed as a first request: the failure in step 1.2 was not saved against the key. Step 1.4 shows that the successful result is saved as usual.

## 2. A replay does not use up a pending failure

A pending failure applies to the next charge that actually runs. A replay runs no charge.

| Step | Endpoint | Key | Body | Expected |
|---|---|---|---|---|
| 2.1 | `/simulation/fail-next-charges` | | `{"count": 1}` | Code `200`, `{"failures_pending": 1}` |
| 2.2 | `/process-payment` | `adr4-order-1` | `{"amount": 100, "currency": "GHS"}` | Code `201` immediately, the `transaction_id` from step 1.3, header `x-cache-hit: true` |
| 2.3 | `/process-payment` | `adr4-order-2` | `{"amount": 100, "currency": "GHS"}` | Code `502` after about 2 seconds. The pending failure was still there for this new charge |
| 2.4 | `/process-payment` | `adr4-order-2` | `{"amount": 100, "currency": "GHS"}` | Code `201` after about 2 seconds, header `x-cache-hit: false` |

## 3. The failure count can be replaced and cleared

| Step | Endpoint | Key | Body | Expected |
|---|---|---|---|---|
| 3.1 | `/simulation/fail-next-charges` | | `{"count": 5}` | Code `200`, `{"failures_pending": 5}` |
| 3.2 | `/simulation/fail-next-charges` | | `{"count": 0}` | Code `200`, `{"failures_pending": 0}` |
| 3.3 | `/process-payment` | `adr4-order-3` | `{"amount": 100, "currency": "GHS"}` | Code `201`, header `x-cache-hit: false`. Nothing fails |
| 3.4 | `/simulation/fail-next-charges` | | `{"count": 101}` | Code `422`. The count must be from 0 to 100 |
| 3.5 | `/simulation/fail-next-charges` | | `{"count": -1}` | Code `422` |

## 4. Duplicates waiting on a failing charge receive the same failure

This section needs two tabs and a longer delay. Set it up as described in the [ADR 0003 test case](adr-0003-in-flight-requests-share-one-charge-task.md#setup-for-this-case): start the server with `PROCESSING_DELAY_SECONDS` set to `10` and open the docs page in tab A and tab B.

Before starting, fill in `/process-payment` in both tabs with these values:

| Field | Value |
|---|---|
| idempotency-key | `adr4-order-4` |
| Request body | `{"amount": 100, "currency": "GHS"}` |

| Step | Tab | Action | Expected |
|---|---|---|---|
| 4.1 | A | Send `{"count": 1}` to `/simulation/fail-next-charges` | Code `200`, `{"failures_pending": 1}` |
| 4.2 | A | Click **Execute** on `/process-payment` | Tab A shows a loading indicator |
| 4.3 | B | Within a few seconds, click **Execute** on `/process-payment` | Tab B also shows a loading indicator |
| 4.4 | both | Wait | Both finish at the same moment with code `502` and the same detail |
| 4.5 | A | Click **Execute** on `/process-payment` again | Code `201` after about 10 seconds, header `x-cache-hit: false` |

Both tabs failed together from a single pending failure, so only one charge was attempted. Step 4.5 succeeds because that one failure has been used.

## 5. The simulation endpoint can be removed

| Step | Action | Expected |
|---|---|---|
| 5.1 | Stop the server. Set `SIMULATION_CONTROLS_ENABLED` to `false` and start it again | The server starts cleanly |
| 5.2 | Reload the docs page | The **Simulation** heading and its endpoint are gone |
| 5.3 | Send `POST /process-payment` with key `adr4-order-5` and body `{"amount": 100, "currency": "GHS"}` | Code `201`. Payments work as normal |
| 5.4 | Stop the server, remove the variable and start it again | The **Simulation** endpoint is back |

Setting and removing the variable:

| Shell | Set | Remove |
|---|---|---|
| PowerShell | `$env:SIMULATION_CONTROLS_ENABLED = "false"` | `Remove-Item Env:SIMULATION_CONTROLS_ENABLED` |
| Command Prompt | `set SIMULATION_CONTROLS_ENABLED=false` | `set SIMULATION_CONTROLS_ENABLED=` |
| macOS or Linux | `export SIMULATION_CONTROLS_ENABLED=false` | `unset SIMULATION_CONTROLS_ENABLED` |
