from typing import Optional
from sqlalchemy import String, Integer, Float, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class DonorEmergencyInteraction(Base):
    """
    Tracks lifecycle interaction events between a blood emergency and a candidate donor.
    Captures immutable dispatch-time snapshot features for future ML response prediction,
    while recording true observed outcomes (contact, delivery, response, acceptance, completion)
    with strict provenance and audit tracking.
    """
    __tablename__ = "donor_emergency_interactions"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    emergency_id: Mapped[str] = mapped_column(String(50), ForeignKey("emergencies.id", ondelete="CASCADE"), nullable=False, index=True)
    donor_id: Mapped[str] = mapped_column(String(50), ForeignKey("donors.id", ondelete="CASCADE"), nullable=False, index=True)
    selected_at: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Immutable Feature Snapshot at Candidate Selection Time (Zero Target Leakage)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    eta_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    time_of_day_hours: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0 to 23.99
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)        # 0=Monday, 6=Sunday
    emergency_priority: Mapped[str] = mapped_column(String(30), nullable=False) # critical, high, medium, low
    compatibility_match_type: Mapped[str] = mapped_column(String(30), nullable=False, default="identical") # identical, universal
    donor_availability_at_selection: Mapped[str] = mapped_column(String(30), nullable=False, default="available") # available, on_call
    donor_total_previous_donations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    donor_days_since_last_donation: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Contact Attempt & Delivery Stage
    contact_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True) # pending, attempted, delivered, failed
    contact_channel: Mapped[Optional[str]] = mapped_column(String(30), nullable=True) # sms, push, call, in_app
    contact_attempted_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    contact_delivered_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Response & Latency Stage
    response_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True) # pending, responded, no_response, expired
    responded_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    response_latency_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Acceptance Stage
    acceptance_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True) # pending, accepted, declined, unreachable
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Donation Completion Stage (Observed at Hospital / Blood Bank)
    completion_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True) # pending, completed, canceled, medically_deferred, did_not_arrive
    completed_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    units_donated: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Provenance, Metadata & Audit
    outcome_source: Mapped[str] = mapped_column(String(50), nullable=False, default="system") # system, dispatcher_portal, donor_app, telephony_webhook, blood_bank_portal, test_fixture
    data_provenance: Mapped[str] = mapped_column(String(50), nullable=False, default="production") # production, synthetic_simulation, test_fixture
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = (
        Index("ix_dint_emergency_donor", "emergency_id", "donor_id"),
        Index("ix_dint_synthetic_provenance", "is_synthetic", "data_provenance"),
    )
