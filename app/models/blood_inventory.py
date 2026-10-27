from typing import Optional
from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class BloodInventory(Base):
    __tablename__ = "blood_inventories"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    blood_bank_id: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("blood_banks.id", ondelete="CASCADE"), nullable=True, index=True)
    hospital_id: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=True, index=True)
    blood_group: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    component: Mapped[str] = mapped_column(String(50), default="whole_blood")
    units_available: Mapped[int] = mapped_column(Integer, default=0)
    units_reserved: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
