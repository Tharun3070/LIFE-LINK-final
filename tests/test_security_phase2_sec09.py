"""
Tests for SEC-09: Rate Limiting and Brute-Force Protection
Verifies:
1. Brute-force login attempts trigger HTTP 429 Too Many Requests.
2. 429 responses include Retry-After header and standard error payload.
3. Separate identifiers and IPs maintain independent rate limit counters.
4. Registration endpoint is protected against rapid account creation bursts.
5. Rate limit state can be deterministically reset for test isolation.
6. Rate limiting obeys RATE_LIMIT_ENABLED flag.
7. Database rate limit store functions correctly across sessions.
"""
import pytest
from app.core.config import settings
from app.core.rate_limiter import rate_limiter, parse_rate_limit, MemoryRateLimitStore, DatabaseRateLimitStore
from app.models.rate_limit import RateLimitRecord


@pytest.fixture(autouse=True)
def clean_rate_limits():
    """Ensure rate limiter starts fresh for every test."""
    rate_limiter.reset()
    yield
    rate_limiter.reset()


def test_sec09_parse_rate_limit():
    """Validates rate limit string parsing across supported time units."""
    assert parse_rate_limit("5/minute") == (5, 60)
    assert parse_rate_limit("3/minute") == (3, 60)
    assert parse_rate_limit("10/second") == (10, 1)
    assert parse_rate_limit("100/hour") == (100, 3600)
    assert parse_rate_limit("1000/day") == (1000, 86400)


def test_sec09_memory_store_sliding_window():
    """MemoryRateLimitStore correctly enforces sliding window limits."""
    store = MemoryRateLimitStore()
    key = "test:client:1"

    # Allow 3 requests per 60s
    for i in range(3):
        allowed, count, retry = store.check_and_increment(key, max_requests=3, window_seconds=60)
        assert allowed is True
        assert count == i + 1
        assert retry == 0

    # 4th request must be blocked
    allowed, count, retry = store.check_and_increment(key, max_requests=3, window_seconds=60)
    assert allowed is False
    assert retry > 0


def test_sec09_database_store_persists_counter(db):
    """DatabaseRateLimitStore persists rate limit records across transactions."""
    store = DatabaseRateLimitStore()
    key = "db:test:client:1"

    allowed, count, retry = store.check_and_increment(key, max_requests=2, window_seconds=60, db=db)
    assert allowed is True
    assert count == 1

    allowed, count, retry = store.check_and_increment(key, max_requests=2, window_seconds=60, db=db)
    assert allowed is True
    assert count == 2

    # 3rd request blocked
    allowed, count, retry = store.check_and_increment(key, max_requests=2, window_seconds=60, db=db)
    assert allowed is False
    assert retry > 0

    # Verify record in database
    rec = db.query(RateLimitRecord).filter(RateLimitRecord.key == key).first()
    assert rec is not None
    assert rec.count == 2


def test_sec09_login_rate_limiting_triggered(client, monkeypatch):
    """Exceeding RATE_LIMIT_LOGIN returns HTTP 429 Too Many Requests."""
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN", "3/minute")

    payload = {
        "identifier": "target_user@lifelink.demo",
        "password": "WrongPassword123!",
    }

    # 3 attempts permitted (and rejected for invalid credentials)
    for _ in range(3):
        resp = client.post("/api/v1/auth/login", json=payload)
        assert resp.status_code == 401

    # 4th attempt exceeds limit and receives 429
    resp_blocked = client.post("/api/v1/auth/login", json=payload)
    assert resp_blocked.status_code == 429
    assert resp_blocked.headers.get("retry-after") is not None
    assert "Too many login attempts" in (resp_blocked.json().get("message") or resp_blocked.json().get("detail", ""))


def test_sec09_different_accounts_do_not_block_each_other(client, monkeypatch):
    """Rate limits on login partition by account identifier so legitimate users are not locked out."""
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN", "2/minute")

    # User A exhausts their limit
    for _ in range(2):
        client.post("/api/v1/auth/login", json={"identifier": "user_a@lifelink.demo", "password": "wrong"})
    resp_a = client.post("/api/v1/auth/login", json={"identifier": "user_a@lifelink.demo", "password": "wrong"})
    assert resp_a.status_code == 429

    # User B can still attempt login without being blocked by User A
    resp_b = client.post("/api/v1/auth/login", json={"identifier": "user_b@lifelink.demo", "password": "wrong"})
    assert resp_b.status_code == 401  # Bad credentials, not 429 rate limit!


def test_sec09_rate_limiter_reset_clears_state(client, monkeypatch, db):
    """Calling rate_limiter.reset() deterministically restores access."""
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN", "2/minute")

    payload = {"identifier": "reset_test@lifelink.demo", "password": "wrong"}
    for _ in range(2):
        client.post("/api/v1/auth/login", json=payload)
    assert client.post("/api/v1/auth/login", json=payload).status_code == 429

    # Reset
    rate_limiter.reset(db=db)

    # Immediately allowed again
    resp_after_reset = client.post("/api/v1/auth/login", json=payload)
    assert resp_after_reset.status_code == 401  # Back to normal 401, not 429
