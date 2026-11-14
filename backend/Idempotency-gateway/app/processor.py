"""Simulated payment processing; no external money movement occurs."""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.schemas import PaymentRequest


class PaymentProcessingError(Exception):
    """The simulated processor failed without making a charge."""


class PaymentProcessor:
    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds

    async def charge(self, payment: PaymentRequest) -> dict[str, str]:
        await asyncio.sleep(self.delay_seconds)
        amount = (
            f"{payment.amount:.0f}"
            if payment.amount == payment.amount.to_integral_value()
            else f"{payment.amount:.2f}"
        )
        return {
            "status": "success",
            "message": f"Charged {amount} {payment.currency}",
            "transaction_id": str(uuid4()),
            "processed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
