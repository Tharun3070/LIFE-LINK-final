"""
Tests for SEC-07: CORS Security
Verifies:
1. Wildcard origins ('*') are rejected in production/staging.
2. Empty CORS_ORIGINS is rejected in production/staging.
3. String comma-separated CORS_ORIGINS parses into discrete origins.
4. Allowed origins receive proper CORS response headers.
5. Disallowed origins are rejected by CORS headers.
"""
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.main import app


def test_sec07_production_wildcard_origin_rejected():
    """Production configuration strictly rejects wildcard ('*') CORS origins."""
    with pytest.raises((ValueError, ValidationError)) as exc_info:
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="e4d909c290d0fb1ca068ffaddf22cbd0e4d909c290d0fb1ca068ffaddf22cbd0",
            DATABASE_URL="postgresql+psycopg://prod:pass@localhost:5432/lifelink_prod",
            CORS_ORIGINS=["*"],
            AUTO_SEED_DATA=False,
        )
    assert "prohibits wildcard" in str(exc_info.value)


def test_sec07_production_empty_cors_origins_rejected():
    """Production configuration rejects empty CORS_ORIGINS list."""
    with pytest.raises((ValueError, ValidationError)) as exc_info:
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="e4d909c290d0fb1ca068ffaddf22cbd0e4d909c290d0fb1ca068ffaddf22cbd0",
            DATABASE_URL="postgresql+psycopg://prod:pass@localhost:5432/lifelink_prod",
            CORS_ORIGINS=[],
            AUTO_SEED_DATA=False,
        )
    assert "CORS_ORIGINS cannot be empty" in str(exc_info.value)


def test_sec07_comma_separated_env_string_parsed_correctly():
    """Comma-separated string of origins from environment is cleanly parsed into a list."""
    s = Settings(
        APP_ENV="development",
        CORS_ORIGINS="http://localhost:3000, https://staging.lifelink.org , http://localhost:5173",
    )
    assert s.CORS_ORIGINS == [
        "http://localhost:3000",
        "https://staging.lifelink.org",
        "http://localhost:5173",
    ]


def test_sec07_allowed_origin_receives_cors_headers(client):
    """Requests with configured origin receive Access-Control-Allow-Origin header."""
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    }
    resp = client.options("/health", headers=headers)
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_sec07_disallowed_origin_rejected(client):
    """Requests with an untrusted, unlisted origin do not receive allow headers."""
    headers = {
        "Origin": "https://malicious-site.attacker.com",
        "Access-Control-Request-Method": "GET",
    }
    resp = client.options("/health", headers=headers)
    assert resp.headers.get("access-control-allow-origin") != "https://malicious-site.attacker.com"
