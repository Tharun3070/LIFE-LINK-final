import os
import pytest
from datetime import datetime, timezone
from unittest.mock import patch
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings, Settings
from app.models.consent import Consent
from app.models.donor import Donor
from app.models.emergency import Emergency, EmergencyEvent
from app.models.interaction import DonorEmergencyInteraction
from app.models.audit import AuditLog
from app.models.user import User
from app.services.interaction_service import InteractionService
from app.schemas.interaction import (
    CandidateSelectionRequest,
    ContactAttemptRequest,
    ContactChannel,
    OutcomeSource,
)
from app.schemas.auth import UserProfileSchema


def test_canonical_database_path_stability():
    """Verify settings resolve canonical database path deterministically."""
    s = Settings()
    resolved_url = s.DATABASE_URL
    assert "lifelink.db" in resolved_url
    # Verify passwords/credentials are not embedded
    assert "password" not in resolved_url.lower()


def test_audit_consent_denial_logged_in_interaction_service(db):
    """
    Verify that InteractionService.record_contact_attempt writes a failed audit log
    when emergency communication consent is missing or False.
    """
    now_str = datetime.now(timezone.utc).isoformat()
    # Create user with consent=False
    user = User(
        id="usr-noconsent-01",
        name="No Consent Donor",
        email="noconsent@example.com",
        hashed_password="hash",
        role="donor",
        session_status="active",
    )
    db.add(user)
    db.commit()

    consent = Consent(
        id="cns-noconsent-01",
        user_id="usr-noconsent-01",
        emergency_communication=False,
        live_location=False,
        donation_requests=False,
        health_data_sharing=False,
        updated_at=now_str,
    )
    db.add(consent)

    donor = Donor(
        id="D-NOCONSENT-01",
        blood_group="O+",
        user_id="usr-noconsent-01",
        status="available",
        eligibility="eligible",
        distance_km=2.5,
        eta_minutes=10,
        is_synthetic=False,
        data_provenance="production",
    )
    db.add(donor)

    emergency = Emergency(
        id="EM-TEST-AUDIT-01",
        type="blood",
        hospital_id="city-hospital-001",
        hospital_name="City General Hospital",
        description="Emergency blood test requirement",
        blood_group="O+",
        units_required=2,
        status="active",
        priority="critical",
        created_at=now_str,
        updated_at=now_str,
    )
    db.add(emergency)
    db.commit()

    staff_user = UserProfileSchema(
        id="usr-staff-01",
        name="Dr. Staff",
        email="staff@lifelink.demo",
        role="doctor",
        status="active",
    )

    sel_res = InteractionService.record_candidate_selection(
        db=db,
        req=CandidateSelectionRequest(
            emergencyId="EM-TEST-AUDIT-01",
            donorId="D-NOCONSENT-01",
            dataProvenance="production",
            isSynthetic=False,
        ),
        current_user=staff_user,
    )
    interaction_id = sel_res.id

    req = ContactAttemptRequest(
        contactChannel=ContactChannel.SMS,
        outcomeSource=OutcomeSource.DISPATCHER_PORTAL,
    )

    with pytest.raises(Exception) as exc_info:
        InteractionService.record_contact_attempt(
            db=db,
            interaction_id=interaction_id,
            req=req,
            current_user=staff_user,
        )

    assert "403" in str(exc_info.value)
    assert "not granted" in str(exc_info.value).lower()

    # Verify that a failed audit log was created
    new_failed_audits = db.query(AuditLog).filter(
        AuditLog.status == "failed",
        AuditLog.resource_id == "D-NOCONSENT-01",
    ).all()
    assert len(new_failed_audits) >= 1
    assert any("not granted" in a.action.lower() for a in new_failed_audits)


def test_synthetic_donor_contact_blocked_and_audited(db):
    """
    Verify that InteractionService blocks attempts to contact synthetic profiles
    and logs an audit record with status='failed'.
    """
    now_str = datetime.now(timezone.utc).isoformat()
    synth_donor = Donor(
        id="D-SYNTH-999",
        blood_group="A+",
        user_id=None,
        status="available",
        eligibility="eligible",
        distance_km=1.0,
        eta_minutes=5,
        is_synthetic=True,
        data_provenance="synthetic_simulation",
    )
    db.add(synth_donor)

    emergency = Emergency(
        id="EM-TEST-AUDIT-02",
        type="blood",
        hospital_id="city-hospital-001",
        hospital_name="City General Hospital",
        description="Synthetic blood test emergency",
        blood_group="A+",
        units_required=1,
        status="active",
        priority="critical",
        created_at=now_str,
        updated_at=now_str,
    )
    db.add(emergency)
    db.commit()

    staff_user = UserProfileSchema(
        id="usr-staff-01",
        name="Dr. Staff",
        email="staff@lifelink.demo",
        role="doctor",
        status="active",
    )

    sel_res = InteractionService.record_candidate_selection(
        db=db,
        req=CandidateSelectionRequest(
            emergencyId="EM-TEST-AUDIT-02",
            donorId="D-SYNTH-999",
            dataProvenance="synthetic_simulation",
            isSynthetic=True,
        ),
        current_user=staff_user,
    )
    interaction_id = sel_res.id

    req = ContactAttemptRequest(
        contactChannel=ContactChannel.SMS,
        outcomeSource=OutcomeSource.DISPATCHER_PORTAL,
    )

    with pytest.raises(Exception) as exc_info:
        InteractionService.record_contact_attempt(
            db=db,
            interaction_id=interaction_id,
            req=req,
            current_user=staff_user,
        )

    assert "403" in str(exc_info.value)
    assert "synthetic" in str(exc_info.value).lower()

    # Check audit log
    audit_entry = db.query(AuditLog).filter(
        AuditLog.status == "failed",
        AuditLog.resource_id == "D-SYNTH-999",
    ).first()
    assert audit_entry is not None
    assert "synthetic" in audit_entry.action.lower()


def test_transaction_rollback_preserves_consistency(db):
    """
    Verify that if a database error occurs during an interaction transaction,
    the rollback leaves the database in a clean state with no partial records.
    """
    initial_interactions = db.query(DonorEmergencyInteraction).count()
    initial_audits = db.query(AuditLog).count()

    # Attempt an operation where commit will fail
    with pytest.raises(SQLAlchemyError):
        with db.begin_nested():
            interaction = DonorEmergencyInteraction(
                id="dint-rollback-test",
                emergency_id="EM-NONEXISTENT",
                donor_id="D-NONEXISTENT",
                selected_at=datetime.now(timezone.utc).isoformat(),
            )
            db.add(interaction)
            # Simulate an intentional DB error
            raise SQLAlchemyError("Simulated write failure")

    assert db.query(DonorEmergencyInteraction).count() == initial_interactions
    assert db.query(AuditLog).count() == initial_audits


def test_no_sensitive_data_in_audit_records(db):
    """
    Verify that existing and newly generated audit records do not contain
    passwords, hashed passwords, access tokens, or bearer headers in action/resource strings.
    """
    audits = db.query(AuditLog).all()
    sensitive_keywords = ["password", "secret", "bearer ", "eyj"]
    for a in audits:
        action_lower = (a.action or "").lower()
        resource_lower = (a.resource or "").lower()
        for kw in sensitive_keywords:
            assert kw not in action_lower, f"Sensitive term '{kw}' found in audit action: {a.id}"
            assert kw not in resource_lower, f"Sensitive term '{kw}' found in audit resource: {a.id}"


def test_candidate_selection_idempotency(db):
    """
    Verify that selecting the same candidate twice returns the existing active interaction
    without creating a duplicate pending interaction.
    """
    staff_user = UserProfileSchema(
        id="usr-staff-01",
        name="Dr. Staff",
        email="staff@lifelink.demo",
        role="doctor",
        status="active",
    )
    req = CandidateSelectionRequest(
        emergencyId="BL-102",
        donorId="D-101",
        dataProvenance="production",
        isSynthetic=False,
    )
    res1 = InteractionService.record_candidate_selection(db=db, req=req, current_user=staff_user)
    count1 = db.query(DonorEmergencyInteraction).count()

    res2 = InteractionService.record_candidate_selection(db=db, req=req, current_user=staff_user)
    count2 = db.query(DonorEmergencyInteraction).count()

    assert res1.id == res2.id
    assert count1 == count2


def test_invalid_transition_delivery_before_attempt(db):
    """Cannot record delivery for an unattempted (pending) interaction."""
    staff_user = UserProfileSchema(
        id="usr-staff-01",
        name="Dr. Staff",
        email="staff@lifelink.demo",
        role="doctor",
        status="active",
    )
    sel = InteractionService.record_candidate_selection(
        db=db,
        req=CandidateSelectionRequest(
            emergencyId="BL-102",
            donorId="D-101",
        ),
        current_user=staff_user,
    )
    from app.schemas.interaction import ContactDeliveredRequest
    with pytest.raises(Exception) as exc:
        InteractionService.record_contact_delivery(
            db=db,
            interaction_id=sel.id,
            req=ContactDeliveredRequest(outcomeSource=OutcomeSource.DISPATCHER_PORTAL),
            current_user=staff_user,
        )
    assert "400" in str(exc.value)


def test_reject_conflicting_second_response(db):
    """Cannot submit a second conflicting response once a response is recorded."""
    staff_user = UserProfileSchema(
        id="usr-staff-01",
        name="Dr. Staff",
        email="staff@lifelink.demo",
        role="doctor",
        status="active",
    )
    sel = InteractionService.record_candidate_selection(
        db=db,
        req=CandidateSelectionRequest(emergencyId="BL-102", donorId="D-101"),
        current_user=staff_user,
    )
    InteractionService.record_contact_attempt(
        db=db,
        interaction_id=sel.id,
        req=ContactAttemptRequest(contactChannel=ContactChannel.SMS),
        current_user=staff_user,
    )

    from app.schemas.interaction import DonorResponseRecordRequest
    # First response: Accepted
    InteractionService.record_donor_response(
        db=db,
        interaction_id=sel.id,
        req=DonorResponseRecordRequest(accepted=True, outcomeSource=OutcomeSource.DISPATCHER_PORTAL),
        current_user=staff_user,
    )

    # Second response attempt: Must be rejected with 400
    with pytest.raises(Exception) as exc:
        InteractionService.record_donor_response(
            db=db,
            interaction_id=sel.id,
            req=DonorResponseRecordRequest(accepted=False, rejectionReason="changed mind", outcomeSource=OutcomeSource.DISPATCHER_PORTAL),
            current_user=staff_user,
        )
    assert "400" in str(exc.value)
    assert "already been recorded" in str(exc.value)


def test_donor_cannot_dispatch_candidate_rbac(client, donor_token):
    """Donors are prohibited by RBAC from selecting candidates or dispatching contacts."""
    res = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    assert res.status_code == 403

