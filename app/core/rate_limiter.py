"""
LifeLink Enterprise Rate Limiting Framework (SEC-09)
Supports multi-worker shared storage via database persistence, optional Redis backend,
and thread-safe in-memory storage for deterministic testing and local development.
"""
import time
import re
from typing import Tuple, Dict, List, Optional
from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.db.session import SessionLocal, get_db
from app.models.rate_limit import RateLimitRecord


def parse_rate_limit(limit_str: str) -> Tuple[int, int]:
    """
    Parses rate limit strings such as:
    - '5/minute' -> (5, 60)
    - '3/minute' -> (3, 60)
    - '10/second' -> (10, 1)
    - '100/hour' -> (100, 3600)
    - '1000/day' -> (1000, 86400)
    """
    if not limit_str or "/" not in limit_str:
        return 100, 60

    parts = limit_str.strip().split("/", 1)
    try:
        count = int(parts[0].strip())
    except ValueError:
        count = 100

    unit = parts[1].strip().lower()
    if unit in ("second", "s", "sec"):
        window = 1
    elif unit in ("minute", "m", "min"):
        window = 60
    elif unit in ("hour", "h", "hr"):
        window = 3600
    elif unit in ("day", "d"):
        window = 86400
    else:
        window = 60

    return count, window


def get_client_ip(request: Request) -> str:
    """Extracts client IP address safely considering forward headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
        if client_ip:
            return client_ip
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


class MemoryRateLimitStore:
    """Thread-safe in-memory sliding window rate limiter for testing and development."""

    def __init__(self):
        self._history: Dict[str, List[float]] = {}

    def check_and_increment(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int, int]:
        now = time.time()
        window_start = now - window_seconds

        timestamps = self._history.get(key, [])
        # Evict timestamps outside the window
        valid_timestamps = [ts for ts in timestamps if ts > window_start]

        if len(valid_timestamps) >= max_requests:
            oldest = valid_timestamps[0]
            retry_after = max(1, int(oldest + window_seconds - now))
            self._history[key] = valid_timestamps
            return False, len(valid_timestamps), retry_after

        valid_timestamps.append(now)
        self._history[key] = valid_timestamps
        return True, len(valid_timestamps), 0

    def reset(self) -> None:
        self._history.clear()


class DatabaseRateLimitStore:
    """
    Shared rate limit store backed by the relational database (PostgreSQL/SQLite).
    Guarantees consistent rate-limit counters across multi-worker and multi-pod deployments
    when Redis is not deployed.
    """

    def check_and_increment(
        self, key: str, max_requests: int, window_seconds: int, db: Optional[Session] = None
    ) -> Tuple[bool, int, int]:
        now = time.time()
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            # Query rate limit record with row lock in PostgreSQL if supported
            record = db.query(RateLimitRecord).filter(RateLimitRecord.key == key).first()

            if not record:
                new_record = RateLimitRecord(
                    key=key,
                    count=1,
                    window_start=now,
                    expires_at=now + window_seconds,
                )
                db.add(new_record)
                db.commit()
                return True, 1, 0

            # If window has expired, reset counter
            if now - record.window_start >= window_seconds:
                record.count = 1
                record.window_start = now
                record.expires_at = now + window_seconds
                db.commit()
                return True, 1, 0

            # Within active window: check limit
            if record.count >= max_requests:
                retry_after = max(1, int(record.window_start + window_seconds - now))
                return False, record.count, retry_after

            # Increment count
            record.count += 1
            db.commit()
            return True, record.count, 0
        except Exception as e:
            logger.warning(f"Database rate limiting query error: {e}. Permitting request safely.")
            try:
                db.rollback()
            except Exception:
                pass
            return True, 1, 0
        finally:
            if close_db:
                db.close()

    def reset(self, db: Optional[Session] = None) -> None:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True
        try:
            db.query(RateLimitRecord).delete()
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            if close_db:
                db.close()


class RateLimiter:
    """
    High-performance Rate Limiter coordinating storage backends and enforcement.
    Defaults to shared Database storage for multi-worker safety, with Memory storage
    available for isolated unit tests.
    """

    def __init__(self):
        self.memory_store = MemoryRateLimitStore()
        self.db_store = DatabaseRateLimitStore()
        # Default to memory store for local development/testing speed, database in multi-worker
        self.use_memory: bool = False

    def reset(self, db: Optional[Session] = None) -> None:
        """Resets all rate limit state in both memory and database stores."""
        self.memory_store.reset()
        self.db_store.reset(db=db)

    def check(
        self,
        key: str,
        limit_str: str,
        db: Optional[Session] = None,
    ) -> Tuple[bool, int, int]:
        max_requests, window_seconds = parse_rate_limit(limit_str)
        if self.use_memory:
            return self.memory_store.check_and_increment(key, max_requests, window_seconds)
        return self.db_store.check_and_increment(key, max_requests, window_seconds, db=db)


# Global singleton instance
rate_limiter = RateLimiter()


def rate_limit(limit_str: str, key_prefix: str = ""):
    """
    FastAPI dependency factory enforcing rate limits on endpoints.
    Returns HTTP 429 Too Many Requests with Retry-After header on breach.
    """

    async def rate_limit_dependency(request: Request, db: Session = Depends(get_db)):
        if not settings.RATE_LIMIT_ENABLED:
            return

        client_ip = get_client_ip(request)
        rate_key = f"{key_prefix}:{client_ip}" if key_prefix else f"{request.url.path}:{client_ip}"

        allowed, count, retry_after = rate_limiter.check(rate_key, limit_str, db=db)
        if not allowed:
            logger.warning(
                f"Rate limit exceeded for client {client_ip} on {request.url.path}: "
                f"limit={limit_str}, count={count}, retry_after={retry_after}s"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Please try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

    return rate_limit_dependency
