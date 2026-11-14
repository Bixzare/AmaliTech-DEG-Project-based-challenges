# Manual test cases

These are step-by-step checks you can run by hand in the interactive API docs. There is one file per architecture decision record in [docs/adr](../docs/adr), and each one exercises the behaviour that ADR describes.

The automated suite in [tests](../tests) covers the same behaviour and more. These cases are for seeing it work yourself.

| Test case | Covers |
|---|---|
| [ADR 0001](adr-0001-fastapi-and-in-memory-store.md) | The server starts, serves the docs, and keeps records in process memory |
| [ADR 0002](adr-0002-request-validation-and-fingerprinting.md) | Key and body validation, replay of the same request, rejection of a different body |
| [ADR 0003](adr-0003-in-flight-requests-share-one-charge-task.md) | Duplicates that arrive mid-charge, conflicts mid-charge, a client disconnecting |

## Before you start

1. Start the server as described in the [project README](../README.md#setup).
2. Open the interactive docs at <http://127.0.0.1:8000/docs>.

## Sending a request from the docs page

1. Click **POST /process-payment** to expand it, then click **Try it out**.
2. Type the key into the **idempotency-key** field.
3. Replace the **Request body** with the JSON given in the step.
4. Click **Execute**.
5. Read the result under **Server response**: the **Code** column shows the status, **Response body** shows the JSON, and **Response headers** shows `x-cache-hit`.

A first request for a key takes about 2 seconds, because the payment processor is simulated with a delay. A replay returns immediately.

Each test case uses its own keys, so the cases can be run in any order. To run a case a second time, restart the server first so the keys are new again.
