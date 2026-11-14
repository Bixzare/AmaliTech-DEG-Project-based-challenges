"""Payment input validation."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0, decimal_places=2, max_digits=12)
    currency: str = Field(pattern=r"^[A-Z]{3}$", min_length=3, max_length=3)
