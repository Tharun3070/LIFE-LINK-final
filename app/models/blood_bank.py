from typing import Optional
from sqlalchemy import String, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class BloodBank(Base):
    __tablename__ = "blood_banks"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False, default="Coimbatore")
    district: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default="Coimbatore")
    pincode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    contact_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    services: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hospital_id: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("hospitals.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    data_provenance: Mapped[str] = mapped_column(String(50), default="production")
