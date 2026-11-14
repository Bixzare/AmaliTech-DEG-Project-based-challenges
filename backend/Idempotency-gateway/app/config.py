"""Validated application settings, loaded once when the app is created."""

import math
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    processing_delay_seconds: float = 2.0
    idempotency_ttl_seconds: float = 86400.0
    idempotency_sweep_interval_seconds: float = 60.0
    simulation_controls_enabled: bool = True

    def __post_init__(self) -> None:
        for name, allow_zero in (
            ("processing_delay_seconds", True),
            ("idempotency_ttl_seconds", False),
            ("idempotency_sweep_interval_seconds", False),
        ):
            rule = "a finite number greater than or equal to 0" if allow_zero else (
                "a finite number greater than 0"
            )
            message = f"{name.upper()} must be {rule}."
            try:
                value = float(getattr(self, name))
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(message) from exc
            if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
                raise ValueError(message)
            object.__setattr__(self, name, value)

        simulation_value = str(self.simulation_controls_enabled).lower()
        if simulation_value not in {"true", "false", "1", "0"}:
            raise ValueError("SIMULATION_CONTROLS_ENABLED must be true, false, 1 or 0.")
        object.__setattr__(
            self, "simulation_controls_enabled", simulation_value in {"true", "1"}
        )

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            processing_delay_seconds=os.getenv("PROCESSING_DELAY_SECONDS", "2.0"),
            idempotency_ttl_seconds=os.getenv("IDEMPOTENCY_TTL_SECONDS", "86400"),
            idempotency_sweep_interval_seconds=os.getenv(
                "IDEMPOTENCY_SWEEP_INTERVAL_SECONDS", "60"
            ),
            simulation_controls_enabled=os.getenv("SIMULATION_CONTROLS_ENABLED", "true"),
        )
