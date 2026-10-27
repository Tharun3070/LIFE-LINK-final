"""
Tests for SEC-06: JWT Secret and Configuration Security
Verifies:
1. Missing JWT secret fails validation in production/staging.
2. Known insecure defaults and placeholder secrets fail validation.
3. Short secrets (< 32 chars) fail validation.
4. Error messages do not print or leak secret values.
5. Safe local development environment boots without manual secrets.
6. Valid, strong production secrets succeed.
"""
import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_sec06_production_missing_jwt_secret_fails():
    """Missing JWT secret in production environment raises ValueError."""
    with pytest.raises((ValueError, ValidationError)) as exc_info:
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="",
            DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/lifelink_prod",
            CORS_ORIGINS=["https://app.lifelink.org"],
            AUTO_SEED_DATA=False,
        )
    assert "Invalid JWT_SECRET_KEY" in str(exc_info.value)


def test_sec06_production_known_insecure_defaults_fail():
    """Known default and placeholder JWT secrets fail production boot."""
    insecure_keys = [
        "dev_insecure_jwt_secret_key_change_in_production_lifelink_2026",
        "change_this_secret_in_production_lifelink_jwt_key",
        "lifelink-super-secret-key-change-in-production-2026",
        "changeme",
        "secret",
        "your_secret_key",
        "placeholder",
        "admin",
        "password",
    ]
    for key in insecure_keys:
        with pytest.raises((ValueError, ValidationError)) as exc_info:
            Settings(
                APP_ENV="production",
                JWT_SECRET_KEY=key,
                DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/lifelink_prod",
                CORS_ORIGINS=["https://app.lifelink.org"],
                AUTO_SEED_DATA=False,
            )
        assert "Invalid JWT_SECRET_KEY" in str(exc_info.value)


def test_sec06_production_short_secret_fails():
    """Production secret under 32 characters is rejected."""
    with pytest.raises((ValueError, ValidationError)) as exc_info:
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="short-secret-only-24-char",
            DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/lifelink_prod",
            CORS_ORIGINS=["https://app.lifelink.org"],
            AUTO_SEED_DATA=False,
        )
    assert "at least 32 characters" in str(exc_info.value)


def test_sec06_error_message_does_not_leak_secret():
    """Validation failure messages must never print or expose the secret value."""
    secret_value = "secret_candidate_dev_insecure_val_12345"
    with pytest.raises((ValueError, ValidationError)) as exc_info:
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY=secret_value,
            DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/lifelink_prod",
            CORS_ORIGINS=["https://app.lifelink.org"],
            AUTO_SEED_DATA=False,
        )
    # The actual secret string must NEVER appear in the error message
    assert secret_value not in str(exc_info.value)


def test_sec06_local_development_works_with_defaults():
    """Local development environment preserves smooth workflow with default settings."""
    s = Settings(
        APP_ENV="development",
        JWT_SECRET_KEY="dev_insecure_jwt_secret_key_change_in_production_lifelink_2026",
        DATABASE_URL="sqlite:///./lifelink.db",
        AUTO_SEED_DATA=True,
    )
    assert s.APP_ENV == "development"
    assert s.JWT_SECRET_KEY is not None


def test_sec06_valid_production_secret_succeeds():
    """A valid, high-entropy 64-character hex secret passes production validation."""
    strong_secret = "e4d909c290d0fb1ca068ffaddf22cbd0e4d909c290d0fb1ca068ffaddf22cbd0"
    s = Settings(
        APP_ENV="production",
        JWT_SECRET_KEY=strong_secret,
        DATABASE_URL="postgresql+psycopg://prod_user:SecurePass123!@db.lifelink.org:5432/lifelink_production",
        CORS_ORIGINS=["https://app.lifelink.org", "https://admin.lifelink.org"],
        AUTO_SEED_DATA=False,
    )
    assert s.APP_ENV == "production"
    assert len(s.JWT_SECRET_KEY) >= 32
