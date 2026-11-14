# Test case: ADR 0002, request validation and body fingerprinting

Checks [ADR 0002](../docs/adr/0002-request-validation-and-fingerprinting.md): requests are validated before a key is recorded, the same payment replays whatever its JSON formatting, and a key cannot be reused for a different payment.

See [README.md](README.md) for how to send a request from the docs page. All steps use `POST /process-payment`.

## 1. The key is required

| Step | Key | Body | Expected |
|---|---|---|---|
| 1.1 | leave the field empty | `{"amount": 100, "currency": "GHS"}` | Code `400`, detail mentions `Idempotency-Key`, returned immediately |

## 2. An invalid body is rejected and does not use up the key

| Step | Key | Body | Expected |
|---|---|---|---|
| 2.1 | `adr2-order-1` | `{"amount": -5, "currency": "GHS"}` | Code `422`, detail says the amount should be greater than 0 |
| 2.2 | `adr2-order-1` | `{"amount": 5, "currency": "ghs"}` | Code `422`, the currency must be three uppercase letters |
| 2.3 | `adr2-order-1` | `{"amount": 5, "currency": "GHS", "note": "x"}` | Code `422`, extra inputs are not permitted |
| 2.4 | `adr2-order-1` | `{"amount": 5.001, "currency": "GHS"}` | Code `422`, at most two decimal places |
| 2.5 | `adr2-order-1` | `{"amount": 5, "currency": "GHS"}` | Code `201` after about 2 seconds, message `Charged 5 GHS`, header `x-cache-hit: false` |

Step 2.5 is the point of this section. The four rejected requests did not record the key, so the corrected request is processed as a first request.

## 3. The same payment replays, whatever its formatting

| Step | Key | Body | Expected |
|---|---|---|---|
| 3.1 | `adr2-order-2` | `{"amount": 100, "currency": "GHS"}` | Code `201` after about 2 seconds, message `Charged 100 GHS`, header `x-cache-hit: false`. Note the `transaction_id` |
| 3.2 | `adr2-order-2` | `{"amount": 100, "currency": "GHS"}` | Code `201` immediately, the same `transaction_id`, header `x-cache-hit: true` |
| 3.3 | `adr2-order-2` | `{"currency": "GHS", "amount": 100}` | Same as 3.2. Key order does not matter |
| 3.4 | `adr2-order-2` | `{"amount": 100.00, "currency": "GHS"}` | Same as 3.2. `100` and `100.00` are the same amount |

## 4. A key cannot be reused for a different payment

Continue with the key from section 3.

| Step | Key | Body | Expected |
|---|---|---|---|
| 4.1 | `adr2-order-2` | `{"amount": 500, "currency": "GHS"}` | Code `409` immediately, detail `Idempotency key already used for a different request body.`, no `x-cache-hit` header |
| 4.2 | `adr2-order-2` | `{"amount": 100, "currency": "USD"}` | Code `409`, same detail |
| 4.3 | `adr2-order-2` | `{"amount": 100, "currency": "GHS"}` | Code `201` immediately, the `transaction_id` from step 3.1, header `x-cache-hit: true` |

Step 4.3 shows that the rejected requests did not disturb the saved payment.

## 5. Different keys are different payments

| Step | Key | Body | Expected |
|---|---|---|---|
| 5.1 | `adr2-order-3` | `{"amount": 100, "currency": "GHS"}` | Code `201` after about 2 seconds, header `x-cache-hit: false`, and a `transaction_id` different from step 3.1 |
