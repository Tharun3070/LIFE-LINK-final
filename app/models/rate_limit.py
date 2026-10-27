from sqlalchemy import String, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class RateLimitRecord(Base):
    """
    Persistent store for distributed rate limiting across multiple worker processes.
    Enables shared rate-limiting counters when Redis is unavailable or optional.
    """
    __tablename__ = "rate_limit_records"

    key: Mapped[str] = mapped_column(String(200), primary_key=True, index=True)
    count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    window_start: Mapped[float] = mapped_column(Float, nullable=False)
    expires_at: Mapped[float] = mapped_column(Float, nullable=False, index=True)
