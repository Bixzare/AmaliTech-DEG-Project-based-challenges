"""HTTP endpoints for the payment gateway."""

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.schemas import PaymentRequest

router = APIRouter()


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

    body = await request.app.state.processor.charge(payment)
    return JSONResponse(status_code=201, content=body, headers={"X-Cache-Hit": "false"})
