"""Payment input validation and canonical request fingerprinting."""

import hashlib
import json
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0, decimal_places=2, max_digits=12)
    currency: str = Field(pattern=r"^[A-Z]{3}$", min_length=3, max_length=3)


def payment_fingerprint(payment: PaymentRequest) -> str:
    payload = {
        "amount": str(payment.amount.quantize(Decimal("0.01"))),
        "currency": payment.currency,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
