from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    live_location: Mapped[bool] = mapped_column(Boolean, default=True)
    emergency_communication: Mapped[bool] = mapped_column(Boolean, default=True)
    donation_requests: Mapped[bool] = mapped_column(Boolean, default=True)
    health_data_sharing: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[str] = mapped_column(String(50), nullable=False)
