from sqlalchemy import String, Boolean, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Hospital(Base):
    __tablename__ = "hospitals"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False, default="Bengaluru")
    lat: Mapped[float] = mapped_column(Float, nullable=True)
    lng: Mapped[float] = mapped_column(Float, nullable=True)
    type: Mapped[str] = mapped_column(String(50), default="general")
    category: Mapped[str] = mapped_column(String(50), default="hospital") # hospital, clinic, blood_bank
    district: Mapped[str] = mapped_column(String(100), nullable=True, default="Coimbatore")
    pincode: Mapped[str] = mapped_column(String(20), nullable=True)
    services: Mapped[str] = mapped_column(String(255), nullable=True)
    blood_bank_available: Mapped[bool] = mapped_column(Boolean, default=False)
    organ_transplant_center: Mapped[bool] = mapped_column(Boolean, default=False)
    emergency_bays: Mapped[int] = mapped_column(Integer, default=0)
    contact_number: Mapped[str] = mapped_column(String(255), nullable=True)
    is_current_hospital: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(50), nullable=True)
    updated_at: Mapped[str] = mapped_column(String(50), nullable=True)
    data_provenance: Mapped[str] = mapped_column(String(50), default="production")

