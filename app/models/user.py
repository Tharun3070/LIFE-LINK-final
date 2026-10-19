from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    role_title: Mapped[str] = mapped_column(String(100), nullable=True)
    hospital_id: Mapped[str] = mapped_column(String(50), ForeignKey("hospitals.id", ondelete="SET NULL"), nullable=True, index=True)
    hospital_name: Mapped[str] = mapped_column(String(150), nullable=True)
    organization: Mapped[str] = mapped_column(String(150), nullable=True)
    avatar: Mapped[str] = mapped_column(String(255), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[str] = mapped_column(String(50), nullable=True)
    session_status: Mapped[str] = mapped_column(String(30), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
