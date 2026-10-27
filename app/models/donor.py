from sqlalchemy import String, Integer, Float, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Donor(Base):
    __tablename__ = "donors"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    blood_group: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    eta_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    eligibility: Mapped[str] = mapped_column(String(30), default="eligible") # eligible, ineligible, pending_review
    eligibility_reason: Mapped[str] = mapped_column(String(255), nullable=True)
    
    # Candidate ranking scores (default neutral values for unranked profiles; never fabricated)
    response_probability: Mapped[int] = mapped_column(Integer, default=50)
    reliability_score: Mapped[int] = mapped_column(Integer, default=50)
    reachability_score: Mapped[int] = mapped_column(Integer, default=50)
    ai_rank: Mapped[int] = mapped_column(Integer, default=999)
    
    status: Mapped[str] = mapped_column(String(30), default="available", index=True) # available, contacted, accepted, declined
    location_consent_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    last_donation_days: Mapped[int] = mapped_column(Integer, nullable=True)
    historical_acceptance_rate: Mapped[int] = mapped_column(Integer, default=0)
    contacted_at: Mapped[str] = mapped_column(String(50), nullable=True)
    responded_at: Mapped[str] = mapped_column(String(50), nullable=True)
    
    lat: Mapped[float] = mapped_column(Float, nullable=True)
    lng: Mapped[float] = mapped_column(Float, nullable=True)

    # Dataset Attributes (Coimbatore & Regional Coverage)
    name: Mapped[str] = mapped_column(String(150), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=True, default="Coimbatore")
    district: Mapped[str] = mapped_column(String(100), nullable=True, default="Coimbatore")
    pincode: Mapped[str] = mapped_column(String(20), nullable=True)
    contact_number: Mapped[str] = mapped_column(String(50), nullable=True)
    email: Mapped[str] = mapped_column(String(120), nullable=True)
    created_at: Mapped[str] = mapped_column(String(50), nullable=True)
    updated_at: Mapped[str] = mapped_column(String(50), nullable=True)

    # Provenance & Simulation Integrity
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    data_provenance: Mapped[str] = mapped_column(String(50), default="production")  # production, synthetic_registry, test_fixture
    simulated_coordinates: Mapped[bool] = mapped_column(Boolean, default=False)

