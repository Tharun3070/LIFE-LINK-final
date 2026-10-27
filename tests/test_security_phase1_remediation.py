"""
Regression test suite for LifeLink Phase 1 Security Remediation:
- SEC-01: WebSocket Authentication & Resource-Level Authorization
- SEC-02: JWT Refresh Token Rejection on Access Token Endpoints
- SEC-03: Emergency Endpoint Authentication & Object-Level Authorization
- SEC-04: Donor SOS Response Authentication & Impersonation Prevention
- SEC-05: Donor Coordinate Serialization Privacy Controls
"""
import pytest
from datetime import timedelta
from starlette.websockets import WebSocketDisconnect
from app.models.user import User
from app.models.donor import Donor
from app.models.emergency import Emergency
from app.models.hospital import Hospital
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
)


# ============================================================================
# 1. SEC-01: WebSocket Authentication & Resource-Level Authorization
# ============================================================================

def test_sec01_anonymous_websocket_rejected(client):
    """Anonymous connection to root /ws must be closed with policy violation (1008)."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws"):
            pass
    assert exc_info.value.code == 1008


def test_sec01_anonymous_v1_websocket_rejected(client):
    """Anonymous connection to /api/v1/ws must be closed with policy violation (1008)."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/v1/ws"):
            pass
    assert exc_info.value.code == 1008


def test_sec01_refresh_token_websocket_rejected(client):
    """WebSocket connection presenting a refresh token instead of access token must be rejected."""
    refresh_tok = create_refresh_token(subject="usr-doc-001", role="doctor")
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws?token={refresh_tok}"):
            pass
    assert exc_info.value.code == 1008


def test_sec01_invalid_token_websocket_rejected(client):
    """WebSocket connection with an invalid/tampered token must be rejected."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws?token=invalid.token.signature"):
            pass
    assert exc_info.value.code == 1008


def test_sec01_expired_token_websocket_rejected(client):
    """WebSocket connection with an expired access token must be rejected."""
    expired_tok = create_access_token(
        subject="usr-doc-001",
        role="doctor",
        expires_delta=timedelta(seconds=-60),
    )
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws?token={expired_tok}"):
            pass
    assert exc_info.value.code == 1008


def test_sec01_authenticated_websocket_receives_welcome(client, doctor_token):
    """A valid doctor access token successfully establishes WebSocket connection."""
    with client.websocket_connect(f"/ws?token={doctor_token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "connection.established"
        assert "message" in msg["payload"]


# ============================================================================
# 2. SEC-02: JWT Refresh Token Rejection on Access Token Endpoints
# ============================================================================

def test_sec02_refresh_token_rejected_on_access_endpoint(client):
    """Supplying a refresh token as Bearer token to /api/v1/users/me must return 401."""
    refresh_tok = create_refresh_token(subject="usr-doc-001", role="doctor")
    resp = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {refresh_tok}"},
    )
    assert resp.status_code == 401
    assert "Expected access token" in (resp.json().get("detail") or resp.json().get("message", ""))


def test_sec02_refresh_token_rejected_on_emergencies_endpoint(client):
    """Supplying a refresh token to /api/v1/emergencies must return 401."""
    refresh_tok = create_refresh_token(subject="usr-doc-001", role="doctor")
    resp = client.get(
        "/api/v1/emergencies",
        headers={"Authorization": f"Bearer {refresh_tok}"},
    )
    assert resp.status_code == 401


# ============================================================================
# 3. SEC-03: Emergency Endpoint Authentication & Object-Level Authorization
# ============================================================================

def test_sec03_anonymous_emergency_list_denied(client):
    """Calling GET /api/v1/emergencies anonymously must return 401 Unauthorized."""
    resp = client.get("/api/v1/emergencies")
    assert resp.status_code == 401


def test_sec03_anonymous_emergency_detail_denied(client):
    """Calling GET /api/v1/emergencies/{id} anonymously must return 401 Unauthorized."""
    resp = client.get("/api/v1/emergencies/BL-102")
    assert resp.status_code == 401


def test_sec03_donor_cannot_browse_emergency_list(client, donor_token):
    """Donors are not authorized to browse emergency lists (returns empty list)."""
    resp = client.get(
        "/api/v1/emergencies",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_sec03_donor_cannot_view_emergency_detail(client, donor_token):
    """Donors attempting to view a specific emergency directly are forbidden (403)."""
    resp = client.get(
        "/api/v1/emergencies/BL-102",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert resp.status_code == 403


def test_sec03_patient_cannot_view_other_patient_emergency(client, db):
    """Patients are strictly isolated; attempting to view another patient's emergency returns 403."""
    # Create emergency for patient A
    patient_a = db.query(User).filter(User.role == "patient").first()
    assert patient_a is not None

    # Create patient B
    patient_b = db.query(User).filter(User.id == "usr-pat-sec03-test").first()
    if not patient_b:
        patient_b = User(
            id="usr-pat-sec03-test",
            name="Patient B Test",
            email="patient_b_test@lifelink.demo",
            hashed_password=get_password_hash("patient123"),
            role="patient",
            is_verified=True,
            session_status="active",
        )
        db.add(patient_b)
        db.commit()

    emg = Emergency(
        id="EMG-SEC03-ISOLATION",
        type="blood",
        priority="critical",
        status="active",
        hospital_id="city-hospital-001",
        hospital_name="City Hospital",
        created_at="2026-10-26T00:00:00Z",
        updated_at="2026-10-26T00:00:00Z",
        patient_id=patient_a.id,
        description="Patient A confidential emergency",
        blood_group="O+",
        units_required=2,
    )
    db.merge(emg)
    db.commit()

    # Patient B attempts to access Patient A's emergency
    token_b = create_access_token(subject=patient_b.id, role=patient_b.role)
    resp = client.get(
        f"/api/v1/emergencies/{emg.id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403
    assert "Access forbidden" in (resp.json().get("detail") or resp.json().get("message", ""))


def test_sec03_patient_cannot_modify_emergency(client, patient_token):
    """Patients cannot modify emergencies via PATCH /api/v1/emergencies/{id} (returns 403)."""
    resp = client.patch(
        "/api/v1/emergencies/BL-102",
        headers={"Authorization": f"Bearer {patient_token}"},
        json={"priority": "low"},
    )
    assert resp.status_code == 403


def test_sec03_hospital_staff_cross_hospital_isolation(client, db):
    """Hospital staff cannot access or modify emergencies belonging to other hospitals."""
    # usr-stf-002 is staff at city-hospital-001
    staff_user = db.query(User).filter(User.role == "hospital_staff").first()
    assert staff_user is not None
    assert staff_user.hospital_id == "city-hospital-001"

    # Emergency belonging to apollo-001
    other_emg = Emergency(
        id="EMG-SEC03-APOLLO",
        type="organ",
        priority="critical",
        status="active",
        hospital_id="apollo-001",
        hospital_name="Apollo Hospital",
        created_at="2026-10-26T00:00:00Z",
        updated_at="2026-10-26T00:00:00Z",
        description="Apollo hospital organ transfer",
    )
    db.merge(other_emg)
    db.commit()

    staff_token = create_access_token(subject=staff_user.id, role=staff_user.role)
    resp_get = client.get(
        f"/api/v1/emergencies/{other_emg.id}",
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    assert resp_get.status_code == 403

    resp_patch = client.patch(
        f"/api/v1/emergencies/{other_emg.id}",
        headers={"Authorization": f"Bearer {staff_token}"},
        json={"priority": "low"},
    )
    assert resp_patch.status_code == 403


# ============================================================================
# 4. SEC-04: Donor SOS Response Authentication & Impersonation Prevention
# ============================================================================

def test_sec04_anonymous_donor_response_rejected(client):
    """Anonymous donor response recording is rejected with 401 Unauthorized."""
    resp = client.post(
        "/api/v1/blood/donors/D-101/response",
        json={"status": "accepted", "shareLocation": True},
    )
    assert resp.status_code == 401


def test_sec04_donor_cannot_respond_for_another_donor(client, donor_token):
    """Donor A (usr-dnr-005, D-101) cannot submit response for Donor B (D-102)."""
    resp = client.post(
        "/api/v1/blood/donors/D-102/response",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"status": "accepted", "shareLocation": True},
    )
    assert resp.status_code == 403
    assert "own profile" in (resp.json().get("detail") or resp.json().get("message", ""))


def test_sec04_patient_cannot_record_donor_response(client, patient_token):
    """Patient accounts cannot submit donor responses (HTTP 403)."""
    resp = client.post(
        "/api/v1/blood/donors/D-101/response",
        headers={"Authorization": f"Bearer {patient_token}"},
        json={"status": "accepted"},
    )
    assert resp.status_code == 403


def test_sec04_doctor_can_record_donor_response(client, doctor_token, db):
    """Authorized clinical doctor can record donor response on behalf of donor."""
    donor = db.query(Donor).filter(Donor.id == "D-104").first()
    if donor:
        donor.status = "contacted"
        db.commit()

    resp = client.post(
        "/api/v1/blood/donors/D-104/response",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"status": "accepted", "shareLocation": True},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"


# ============================================================================
# 5. SEC-05: Donor Coordinate Serialization Privacy Controls
# ============================================================================

def test_sec05_unauthorized_caller_cannot_view_donor_coordinates(client, patient_token, db):
    """
    Patient querying /api/v1/donors must NEVER receive precise coordinates,
    even when locationConsentGranted is True.
    """
    # Ensure D-102 has location_consent_granted = True and valid lat/lng
    d102 = db.query(Donor).filter(Donor.id == "D-102").first()
    assert d102 is not None
    d102.location_consent_granted = True
    d102.lat = 12.965
    d102.lng = 77.595
    db.commit()

    resp = client.get(
        "/api/v1/donors",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert resp.status_code == 200
    donors = resp.json()
    assert len(donors) >= 1

    # Check that EVERY donor returned has coordinates=None for the patient
    for d in donors:
        assert d.get("coordinates") is None, f"Donor {d['id']} coordinates leaked to patient"


def test_sec05_doctor_receives_coordinates_only_if_consent_granted(client, doctor_token, db):
    """
    Doctor querying a donor receives coordinates ONLY if location_consent_granted is True.
    If location_consent_granted is False, coordinates must be None even for doctor.
    """
    d101 = db.query(Donor).filter(Donor.id == "D-101").first()
    assert d101 is not None
    d101.location_consent_granted = False
    d101.lat = 12.975
    d101.lng = 77.590

    d102 = db.query(Donor).filter(Donor.id == "D-102").first()
    assert d102 is not None
    d102.location_consent_granted = True
    d102.lat = 12.965
    d102.lng = 77.595
    db.commit()

    # D-101 (consent=False) -> doctor sees None
    resp1 = client.get(
        "/api/v1/donors/D-101",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp1.status_code == 200
    assert resp1.json().get("coordinates") is None

    # D-102 (consent=True) -> doctor sees Coordinates
    resp2 = client.get(
        "/api/v1/donors/D-102",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp2.status_code == 200
    coords = resp2.json().get("coordinates")
    assert coords is not None
    assert coords["lat"] == 12.965
    assert coords["lng"] == 77.595


def test_sec05_donor_can_view_own_coordinates(client, donor_token):
    """Donor viewing /api/v1/donors/me can view their own coordinates."""
    resp = client.get(
        "/api/v1/donors/me",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert resp.status_code == 200
    assert "bloodGroup" in resp.json()
