import pytest

from app.config import Settings
from app.main import create_app


def test_defaults(monkeypatch):
    for name in (
        "PROCESSING_DELAY_SECONDS",
        "IDEMPOTENCY_TTL_SECONDS",
        "IDEMPOTENCY_SWEEP_INTERVAL_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.processing_delay_seconds == 2
    assert settings.idempotency_ttl_seconds == 86400
    assert settings.idempotency_sweep_interval_seconds == 60


def test_valid_environment_overrides(monkeypatch):
    monkeypatch.setenv("PROCESSING_DELAY_SECONDS", "0")
    monkeypatch.setenv("IDEMPOTENCY_TTL_SECONDS", "120")
    monkeypatch.setenv("IDEMPOTENCY_SWEEP_INTERVAL_SECONDS", "0.1")

    settings = Settings.from_env()

    assert settings.processing_delay_seconds == 0
    assert settings.idempotency_ttl_seconds == 120
    assert settings.idempotency_sweep_interval_seconds == 0.1


@pytest.mark.parametrize(
    "field,value",
    [
        ("processing_delay_seconds", -1),
        ("idempotency_ttl_seconds", 0),
        ("idempotency_sweep_interval_seconds", 0),
        ("idempotency_ttl_seconds", -1),
        ("idempotency_sweep_interval_seconds", -1),
        ("processing_delay_seconds", "nan"),
        ("idempotency_ttl_seconds", "inf"),
        ("idempotency_sweep_interval_seconds", "-inf"),
        ("processing_delay_seconds", "invalid"),
    ],
)
def test_invalid_direct_settings(field, value):
    with pytest.raises(ValueError, match=field.upper()):
        Settings(**{field: value})


@pytest.mark.parametrize(
    "name,value",
    [
        ("PROCESSING_DELAY_SECONDS", "-1"),
        ("IDEMPOTENCY_TTL_SECONDS", "0"),
        ("IDEMPOTENCY_SWEEP_INTERVAL_SECONDS", "0"),
        ("PROCESSING_DELAY_SECONDS", "nan"),
        ("IDEMPOTENCY_TTL_SECONDS", "inf"),
        ("IDEMPOTENCY_SWEEP_INTERVAL_SECONDS", "invalid"),
    ],
)
def test_invalid_environment_prevents_app_creation(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        create_app()
