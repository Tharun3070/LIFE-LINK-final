from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    timestamp: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False, default="user") # user, system, ai, donor
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource: Mapped[str] = mapped_column(String(150), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(50), nullable=True, index=True)
    authorization: Mapped[str] = mapped_column(String(150), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="success") # success, failed, pending
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True) # blood, organ, ambulance, system, auth
    ip_address: Mapped[str] = mapped_column(String(50), nullable=True)
    session_id: Mapped[str] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=True)
