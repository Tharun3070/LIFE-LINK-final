from sqlalchemy import String, Integer, Float, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Organ(Base):
    __tablename__ = "organs"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    organ_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True) # kidney, liver, heart, lung, etc.
    source_hospital_id: Mapped[str] = mapped_column(String(50), ForeignKey("hospitals.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_hospital_name: Mapped[str] = mapped_column(String(150), nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    eta_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    
    viability_remaining_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    viability_total_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    viability_level: Mapped[str] = mapped_column(String(20), default="normal") # normal, warning, critical
    
    reachability_score: Mapped[int] = mapped_column(Integer, default=90)
    ai_recommendation: Mapped[str] = mapped_column(String(30), default="proceed") # proceed, caution, do_not_proceed
    ai_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    
    status: Mapped[str] = mapped_column(String(30), default="available", index=True) # available, clinical_review, allocated, etc.
    clinical_review_status: Mapped[str] = mapped_column(String(30), default="pending") # pending, in_review, approved, rejected, not_required
    authorized_coordinator_id: Mapped[str] = mapped_column(String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    lat: Mapped[float] = mapped_column(Float, nullable=True)
    lng: Mapped[float] = mapped_column(Float, nullable=True)
    
    available_at: Mapped[str] = mapped_column(String(50), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(50), nullable=False)
