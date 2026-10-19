from typing import Optional
from sqlalchemy import String, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Emergency(Base):
    __tablename__ = "emergencies"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    patient_id: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False, index=True) # blood, organ, ambulance, multi
    priority: Mapped[str] = mapped_column(String(30), nullable=False, default="critical", index=True) # critical, high, medium, low
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="created", index=True)
    hospital_id: Mapped[str] = mapped_column(String(50), ForeignKey("hospitals.id", ondelete="RESTRICT"), nullable=False, index=True)
    hospital_name: Mapped[str] = mapped_column(String(150), nullable=False)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    updated_at: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    eta: Mapped[int] = mapped_column(Integer, nullable=True)
    assigned_resource_ids: Mapped[str] = mapped_column(Text, nullable=True) # comma or json
    resolved_at: Mapped[str] = mapped_column(String(50), nullable=True)
    
    # Blood specific
    blood_group: Mapped[str] = mapped_column(String(10), nullable=True)
    units_required: Mapped[int] = mapped_column(Integer, nullable=True)

    # Organ specific
    organ_type: Mapped[str] = mapped_column(String(50), nullable=True)

    # Ambulance specific
    origin: Mapped[str] = mapped_column(String(150), nullable=True)
    destination: Mapped[str] = mapped_column(String(150), nullable=True)


class EmergencyEvent(Base):
    __tablename__ = "emergency_events"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    emergency_id: Mapped[str] = mapped_column(String(50), ForeignKey("emergencies.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource: Mapped[str] = mapped_column(String(150), nullable=True)
    authorization: Mapped[str] = mapped_column(String(150), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="success")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=True)
