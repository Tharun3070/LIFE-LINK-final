from unittest.mock import patch
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.models.emergency import Emergency, EmergencyEvent
from app.models.audit import AuditLog
from app.realtime.manager import ws_manager


def test_list_organs(client):
    response = client.get("/api/v1/organs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3


def test_list_organs_available_alias(client):
    response = client.get("/api/v1/organs/available")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3


def test_get_organ_by_id(client):
    response = client.get("/api/v1/organs/ORG-K-001")
    assert response.status_code == 200
    data = response.json()
    assert data["organType"] == "kidney"
    assert data["viabilityLevel"] == "normal"


def test_create_organ_request_persisted_and_audited(client, coordinator_token, db):
    response = client.post(
        "/api/v1/organs/requests",
        headers={"Authorization": f"Bearer {coordinator_token}"},
        json={
            "organType": "heart",
            "recipientHospitalId": "city-hospital-001",
            "urgency": "critical",
            "notes": "Emergency cardiac patient waiting in OR",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "searching"
    assert data["organType"] == "heart"
    assert data["recipientHospitalId"] == "city-hospital-001"
    assert data["recipientHospitalName"] == "City General Hospital"
    assert data["priority"] == "critical"
    assert data["id"].startswith("ORG-")
    assert data["emergencyId"] == data["id"]

    # Verify atomic persistence in SQLite database
    emergency = db.query(Emergency).filter(Emergency.id == data["emergencyId"]).first()
    assert emergency is not None
    assert emergency.type == "organ"
    assert emergency.organ_type == "heart"
    assert emergency.status == "searching"
    assert emergency.priority == "critical"
    assert emergency.hospital_id == "city-hospital-001"

    # Verify timeline event was persisted
    events = db.query(EmergencyEvent).filter(EmergencyEvent.emergency_id == emergency.id).all()
    assert len(events) >= 1
    event_descriptions = [e.action for e in events]
    assert any("created" in desc.lower() for desc in event_descriptions)

    # Verify audit trail entry was recorded
    audit = db.query(AuditLog).filter(
        AuditLog.resource_id == emergency.id
    ).first()
    assert audit is not None
    assert "Organ Emergency SOS" in audit.action
    assert audit.authorization == "Role: transplant_coordinator"
    assert audit.status == "success"
    assert audit.module == "organ"


def test_create_organ_request_missing_or_invalid_hospital(client, coordinator_token, db):
    response = client.post(
        "/api/v1/organs/requests",
        headers={"Authorization": f"Bearer {coordinator_token}"},
        json={
            "organType": "liver",
            "recipientHospitalId": "non-existent-hospital-999",
            "urgency": "urgent",
            "notes": "Invalid hospital test",
        },
    )
    assert response.status_code == 400
    msg = response.json().get("message") or response.json().get("detail", "")
    assert "Hospital with ID 'non-existent-hospital-999' not found" in msg

    # Verify no emergency was persisted for the invalid hospital
    emg = db.query(Emergency).filter(Emergency.hospital_id == "non-existent-hospital-999").first()
    assert emg is None

    # Verify failure audit entry exists
    failed_audit = db.query(AuditLog).filter(
        AuditLog.resource_id == "non-existent-hospital-999"
    ).order_by(AuditLog.timestamp.desc()).first()
    assert failed_audit is not None
    assert "Failed to create" in failed_audit.action
    assert failed_audit.status == "failed"


def test_create_organ_request_invalid_organ_type(client, coordinator_token):
    response = client.post(
        "/api/v1/organs/requests",
        headers={"Authorization": f"Bearer {coordinator_token}"},
        json={
            "organType": "brain",
            "recipientHospitalId": "city-hospital-001",
            "urgency": "critical",
        },
    )
    assert response.status_code == 400
    msg = response.json().get("message") or response.json().get("detail", "")
    assert "Invalid organ type 'brain'" in msg


def test_create_organ_request_unauthorized_roles(client, donor_token, patient_token, staff_token, doctor_token, admin_token):
    payload = {
        "organType": "lung",
        "recipientHospitalId": "city-hospital-001",
        "urgency": "standard",
    }

    # Donor: 403 Forbidden
    res_donor = client.post("/api/v1/organs/requests", headers={"Authorization": f"Bearer {donor_token}"}, json=payload)
    assert res_donor.status_code == 403

    # Patient: 403 Forbidden
    res_patient = client.post("/api/v1/organs/requests", headers={"Authorization": f"Bearer {patient_token}"}, json=payload)
    assert res_patient.status_code == 403

    # Staff (non-coordinator/non-doctor): 403 Forbidden
    res_staff = client.post("/api/v1/organs/requests", headers={"Authorization": f"Bearer {staff_token}"}, json=payload)
    assert res_staff.status_code == 403

    # Doctor: 200 OK
    res_doc = client.post("/api/v1/organs/requests", headers={"Authorization": f"Bearer {doctor_token}"}, json=payload)
    assert res_doc.status_code == 200

    # Admin: 200 OK
    res_admin = client.post("/api/v1/organs/requests", headers={"Authorization": f"Bearer {admin_token}"}, json=payload)
    assert res_admin.status_code == 200


def test_create_organ_request_duplicate_submission_idempotency(client, doctor_token, db):
    payload = {
        "organType": "pancreas",
        "recipientHospitalId": "apollo-001",
        "urgency": "urgent",
        "notes": "Testing duplicate prevention idempotency",
    }

    # First submission
    res1 = client.post("/api/v1/organs/requests", headers={"Authorization": f"Bearer {doctor_token}"}, json=payload)
    assert res1.status_code == 200
    data1 = res1.json()

    # Immediate second submission (within 60-second idempotency window)
    res2 = client.post("/api/v1/organs/requests", headers={"Authorization": f"Bearer {doctor_token}"}, json=payload)
    assert res2.status_code == 200
    data2 = res2.json()

    # Must return the existing emergency and NOT create a duplicate record
    assert data1["emergencyId"] == data2["emergencyId"]
    assert data1["id"] == data2["id"]

    pancreas_count = db.query(Emergency).filter(
        Emergency.hospital_id == "apollo-001",
        Emergency.organ_type == "pancreas",
        Emergency.type == "organ",
    ).count()
    assert pancreas_count == 1


def test_create_organ_request_db_failure_atomic_rollback(client, coordinator_token, db):
    payload = {
        "organType": "cornea",
        "recipientHospitalId": "city-hospital-001",
        "urgency": "standard",
        "notes": "Testing DB failure rollback",
    }

    with patch("app.services.emergency_service.EmergencyService.create", side_effect=SQLAlchemyError("Simulated DB commit error")):
        response = client.post(
            "/api/v1/organs/requests",
            headers={"Authorization": f"Bearer {coordinator_token}"},
            json=payload,
        )
        assert response.status_code == 500

    # Verify no partial cornea emergency record exists
    emg = db.query(Emergency).filter(
        Emergency.hospital_id == "city-hospital-001",
        Emergency.organ_type == "cornea"
    ).first()
    assert emg is None


def test_create_organ_request_websocket_emission_after_commit(client, coordinator_token):
    payload = {
        "organType": "bone_marrow",
        "recipientHospitalId": "city-hospital-001",
        "urgency": "critical",
        "notes": "Testing WS emission sequence",
    }

    events_broadcast = []

    def mock_broadcast_sync(event):
        events_broadcast.append(event)

    with patch.object(ws_manager, "broadcast_sync", side_effect=mock_broadcast_sync):
        response = client.post(
            "/api/v1/organs/requests",
            headers={"Authorization": f"Bearer {coordinator_token}"},
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()

        # Verify broadcast was called with EMERGENCY_CREATED and organType
        assert len(events_broadcast) >= 1
        event = events_broadcast[0]
        assert event.type == "emergency.created"
        assert event.payload["emergencyId"] == data["emergencyId"]
        assert event.payload["organType"] == "bone_marrow"
        assert event.payload["status"] == "searching"


def test_clinical_review_by_transplant_coordinator(client, coordinator_token):
    response = client.post(
        "/api/v1/organs/ORG-K-001/clinical-review",
        headers={"Authorization": f"Bearer {coordinator_token}"},
        json={"decision": "approved", "notes": "Candidate HLA matching verified."},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["clinicalReviewStatus"] == "approved"


def test_clinical_review_unauthorized(client, donor_token):
    response = client.post(
        "/api/v1/organs/ORG-K-001/clinical-review",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"decision": "approved"},
    )
    assert response.status_code == 403


# ==============================================================================
# Phase 3.5 — Dynamic Organ Cold Ischemia Time Regression Tests
# ==============================================================================

def test_dynamic_viability_fresh_organ_has_full_duration(client, db):
    """A fresh organ queried right at available_at has approximately its full duration."""
    from datetime import datetime, timezone
    from app.services.organ_service import OrganService
    from app.models.organ import Organ

    ref_time = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)
    organ = db.query(Organ).filter(Organ.id == "ORG-H-003").first()
    organ.available_at = ref_time.isoformat()
    db.commit()

    with patch.object(OrganService, "now_fn", return_value=ref_time):
        response = client.get("/api/v1/organs/ORG-H-003")
        assert response.status_code == 200
        data = response.json()
        assert data["viabilityRemainingSeconds"] == organ.viability_total_seconds
        assert data["viabilityTotalSeconds"] == organ.viability_total_seconds


def test_dynamic_viability_decreases_as_time_elapses(client, db):
    """Remaining viability decreases proportionally as time elapses."""
    from datetime import datetime, timezone, timedelta
    from app.services.organ_service import OrganService
    from app.models.organ import Organ

    ref_time = datetime(2026, 10, 18, 10, 0, 0, tzinfo=timezone.utc)
    organ = db.query(Organ).filter(Organ.id == "ORG-H-003").first()
    organ.available_at = ref_time.isoformat()
    organ.viability_total_seconds = 21600  # 6 hours
    db.commit()

    # 1 hour elapsed (3600s)
    t1 = ref_time + timedelta(seconds=3600)
    with patch.object(OrganService, "now_fn", return_value=t1):
        res1 = client.get("/api/v1/organs/ORG-H-003")
        assert res1.status_code == 200
        assert res1.json()["viabilityRemainingSeconds"] == 21600 - 3600

    # 2.5 hours elapsed (9000s)
    t2 = ref_time + timedelta(seconds=9000)
    with patch.object(OrganService, "now_fn", return_value=t2):
        res2 = client.get("/api/v1/organs/ORG-H-003")
        assert res2.status_code == 200
        assert res2.json()["viabilityRemainingSeconds"] == 21600 - 9000

    # 5 hours elapsed (18000s)
    t3 = ref_time + timedelta(seconds=18000)
    with patch.object(OrganService, "now_fn", return_value=t3):
        res3 = client.get("/api/v1/organs/ORG-H-003")
        assert res3.status_code == 200
        assert res3.json()["viabilityRemainingSeconds"] == 21600 - 18000


def test_dynamic_viability_expired_organ_clamped_at_zero(client, db):
    """An expired organ returns zero remaining time and never negative values."""
    from datetime import datetime, timezone, timedelta
    from app.services.organ_service import OrganService
    from app.models.organ import Organ

    ref_time = datetime(2026, 10, 18, 8, 0, 0, tzinfo=timezone.utc)
    organ = db.query(Organ).filter(Organ.id == "ORG-H-003").first()
    organ.available_at = ref_time.isoformat()
    organ.viability_total_seconds = 21600  # 6 hours
    db.commit()

    # Exactly expired (6 hours)
    t_exact = ref_time + timedelta(seconds=21600)
    with patch.object(OrganService, "now_fn", return_value=t_exact):
        res = client.get("/api/v1/organs/ORG-H-003")
        assert res.status_code == 200
        assert res.json()["viabilityRemainingSeconds"] == 0

    # Well past expired (24 hours)
    t_past = ref_time + timedelta(hours=24)
    with patch.object(OrganService, "now_fn", return_value=t_past):
        res_past = client.get("/api/v1/organs/ORG-H-003")
        assert res_past.status_code == 200
        assert res_past.json()["viabilityRemainingSeconds"] == 0

    # Days past expired (30 days)
    t_long_past = ref_time + timedelta(days=30)
    with patch.object(OrganService, "now_fn", return_value=t_long_past):
        res_long = client.get("/api/v1/organs/ORG-H-003")
        assert res_long.status_code == 200
        assert res_long.json()["viabilityRemainingSeconds"] == 0


def test_dynamic_viability_missing_or_invalid_timestamp_safe_fallback():
    """Missing or invalid reference timestamps follow documented safe fallback behavior."""
    from app.services.organ_service import OrganService

    # 1. Missing available_at string falls back to stored remaining seconds
    res1 = OrganService.calculate_dynamic_viability(
        total_seconds=21600,
        available_at_str=None,
        fallback_remaining_seconds=10800,
    )
    assert res1 == 10800

    # 2. Empty string falls back to stored remaining seconds
    res2 = OrganService.calculate_dynamic_viability(
        total_seconds=21600,
        available_at_str="",
        fallback_remaining_seconds=12000,
    )
    assert res2 == 12000

    # 3. Invalid/unparseable string falls back to stored remaining seconds
    res3 = OrganService.calculate_dynamic_viability(
        total_seconds=21600,
        available_at_str="not-a-valid-iso-date",
        fallback_remaining_seconds=15000,
    )
    assert res3 == 15000

    # 4. If fallback is greater than total_seconds, clamped to total_seconds
    res4 = OrganService.calculate_dynamic_viability(
        total_seconds=21600,
        available_at_str="invalid",
        fallback_remaining_seconds=999999,
    )
    assert res4 == 21600

    # 5. If both reference timestamp and fallback are missing/invalid, safely returns 0
    res5 = OrganService.calculate_dynamic_viability(
        total_seconds=21600,
        available_at_str="invalid",
        fallback_remaining_seconds=None,
    )
    assert res5 == 0

    # 6. If total_seconds <= 0, safely returns 0
    res6 = OrganService.calculate_dynamic_viability(
        total_seconds=0,
        available_at_str="2026-10-18T10:00:00Z",
    )
    assert res6 == 0


def test_dynamic_viability_timezone_offsets_consistency():
    """Different timezone representations of the exact same moment calculate identical remaining seconds."""
    from datetime import datetime, timezone
    from app.services.organ_service import OrganService

    # 10:00:00 UTC represented three different ways
    ts_utc = "2026-10-18T10:00:00+00:00"
    ts_z = "2026-10-18T10:00:00Z"
    ts_ist = "2026-10-18T15:30:00+05:30"   # 15:30 IST == 10:00 UTC
    ts_edt = "2026-10-18T06:00:00-04:00"   # 06:00 EDT == 10:00 UTC

    # Current time is 11:30:00 UTC (90 minutes = 5400s elapsed)
    now = datetime(2026, 10, 18, 11, 30, 0, tzinfo=timezone.utc)
    total = 21600
    expected_remaining = 21600 - 5400  # 16200

    res_utc = OrganService.calculate_dynamic_viability(total, ts_utc, now=now)
    res_z = OrganService.calculate_dynamic_viability(total, ts_z, now=now)
    res_ist = OrganService.calculate_dynamic_viability(total, ts_ist, now=now)
    res_edt = OrganService.calculate_dynamic_viability(total, ts_edt, now=now)

    assert res_utc == expected_remaining
    assert res_z == expected_remaining
    assert res_ist == expected_remaining
    assert res_edt == expected_remaining


def test_dynamic_viability_future_timestamp_clamped_to_total():
    """If a timestamp is slightly in the future (e.g. clock skew), remaining time is clamped to total_seconds."""
    from datetime import datetime, timezone
    from app.services.organ_service import OrganService

    now = datetime(2026, 10, 18, 10, 0, 0, tzinfo=timezone.utc)
    future_ts = "2026-10-18T10:15:00Z"  # 15 minutes in the future

    res = OrganService.calculate_dynamic_viability(
        total_seconds=21600,
        available_at_str=future_ts,
        now=now,
    )
    assert res == 21600


def test_dynamic_viability_repeated_api_requests_do_not_mutate_db(client, db):
    """Repeated API requests calculate from the reference timestamp and do not mutate or decrement DB rows."""
    from datetime import datetime, timezone, timedelta
    from app.services.organ_service import OrganService
    from app.models.organ import Organ

    ref_time = datetime(2026, 10, 18, 9, 0, 0, tzinfo=timezone.utc)
    organ = db.query(Organ).filter(Organ.id == "ORG-H-003").first()
    original_stored_remaining = organ.viability_remaining_seconds
    organ.available_at = ref_time.isoformat()
    organ.viability_total_seconds = 21600
    db.commit()

    fixed_now = ref_time + timedelta(minutes=45)  # 2700s elapsed
    expected = 21600 - 2700  # 18900

    with patch.object(OrganService, "now_fn", return_value=fixed_now):
        # First request
        res1 = client.get("/api/v1/organs/ORG-H-003")
        assert res1.status_code == 200
        assert res1.json()["viabilityRemainingSeconds"] == expected

        # Second request (must return exact same calculation, not repeatedly decremented)
        res2 = client.get("/api/v1/organs/ORG-H-003")
        assert res2.status_code == 200
        assert res2.json()["viabilityRemainingSeconds"] == expected

        # Third request
        res3 = client.get("/api/v1/organs/ORG-H-003")
        assert res3.status_code == 200
        assert res3.json()["viabilityRemainingSeconds"] == expected

    # Verify underlying database row was NOT modified by read operations
    db.refresh(organ)
    assert organ.viability_remaining_seconds == original_stored_remaining

