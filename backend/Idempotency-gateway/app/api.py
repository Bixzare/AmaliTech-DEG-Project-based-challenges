"""HTTP endpoints for the payment gateway."""

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.processor import PaymentProcessingError
from app.schemas import FailureSimulationRequest, PaymentRequest, payment_fingerprint
from app.store import IdempotencyKeyConflict, StoredResponse

router = APIRouter()
simulation_router = APIRouter(prefix="/simulation", tags=["Simulation"])


@simulation_router.post(
    "/fail-next-charges",
    description=(
        "Controls the simulated processor and would not exist with a real payment processor. "
        "Replace the number of upcoming charges that will fail; zero clears pending failures."
    ),
)
async def fail_next_charges(
    simulation: FailureSimulationRequest, request: Request
) -> dict[str, int]:
    processor = request.app.state.processor
    processor.fail_next(simulation.count)
    return {"failures_pending": processor.failures_pending}


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/process-payment", status_code=201)
async def process_payment(
    payment: PaymentRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None),
) -> JSONResponse:
    key = idempotency_key.strip() if idempotency_key is not None else ""
    if not 1 <= len(key) <= 255:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key must contain 1 to 255 characters after trimming whitespace.",
        )

    fingerprint = payment_fingerprint(payment)

    async def work() -> StoredResponse:
        body = await request.app.state.processor.charge(payment)
        return StoredResponse(status_code=201, body=body)

    try:
        response, replayed = await request.app.state.store.execute(
            ("default", key), fingerprint, work
        )
    except IdempotencyKeyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PaymentProcessingError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Payment processing failed. No charge was made; "
                "retry with the same Idempotency-Key."
            ),
        ) from exc
    return JSONResponse(
        status_code=response.status_code,
        content=response.body,
        headers={"X-Cache-Hit": "true" if replayed else "false"},
    )
