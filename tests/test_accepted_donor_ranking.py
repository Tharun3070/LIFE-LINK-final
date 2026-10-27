"""
LifeLink Dedicated Accepted Donor Arrival Ranking Tests.
Tests the endpoint: GET /api/v1/emergencies/{emergency_id}/accepted-donors/ranking

Verifies:
1. Accepted donors are included in ranking.
2. Pending, declined, unreachable, and cancelled donors are excluded.
3. Donors from other emergencies are excluded.
4. Duplicate interactions for the same donor do not produce duplicate entries.
5. Missing or invalid coordinates are handled safely without fabricating ETAs.
6. Google Maps live routing and deterministic heuristic fallback behaviors.
7. Nonexistent, non-blood, and inactive emergency lifecycle validations.
8. Role-based access control and unauthorized caller rejection.
9. Correct ascending ETA duration sorting.
10. Donor privacy and safe transit status attributions.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, MagicMock
import pytest
import httpx

from app.models.donor import Donor
from app.models.emergency import Emergency
from app.models.hospital import Hospital
from app.models.interaction import DonorEmergencyInteraction
from app.models.user import User
from app.core.security import create_access_token


def _create_interaction(
    db,
    emergency_id: str,
    donor_id: str,
    acceptance_status: str = "accepted",
    completion_status: str = "pending",
    responded_at: str = None,
    distance_km: float = 4.2,
    eta_minutes: int = 12,
) -> DonorEmergencyInteraction:
    now_str = datetime.now(timezone.utc).isoformat()
    inter = DonorEmergencyInteraction(
        id=f"dint-{uuid.uuid4().hex[:12]}",
        emergency_id=emergency_id,
        donor_id=donor_id,
        selected_at=now_str,
        distance_km=distance_km,
        eta_minutes=eta_minutes,
        time_of_day_hours=14.5,
        day_of_week=2,
        emergency_priority="critical",
        compatibility_match_type="identical",
        donor_availability_at_selection="available",
        donor_total_previous_donations=3,
        donor_days_since_last_donation=60,
        contact_status="delivered",
        contact_channel="sms",
        contact_attempted_at=now_str,
        contact_delivered_at=now_str,
        response_status="responded" if acceptance_status != "pending" else "pending",
        responded_at=responded_at or (now_str if acceptance_status != "pending" else None),
        response_latency_seconds=45 if acceptance_status != "pending" else None,
        acceptance_status=acceptance_status,
        completion_status=completion_status,
        outcome_source="dispatcher_portal",
        data_provenance="production",
        is_synthetic=False,
        created_at=now_str,
        updated_at=now_str,
    )
    db.add(inter)
    db.commit()
    db.refresh(inter)
    return inter


def test_accepted_donors_included_in_ranking(client, doctor_token, db):
    """Verifies that donors who explicitly accepted are included in the ranking."""
    # Ensure hospital exists
    hospital = db.query(Hospital).filter(Hospital.id == "hosp-001").first()
    if not hospital:
        hospital = Hospital(
            id="hosp-001",
            name="City General Hospital",
            address="100 Main St",
            city="Bengaluru",
            lat=12.9716,
            lng=77.5946,
            type="general",
            blood_bank_available=True,
        )
        db.add(hospital)
        db.commit()

    # Ensure donor exists
    donor = db.query(Donor).filter(Donor.id == "D-101").first()
    if not donor:
        donor = Donor(
            id="D-101",
            blood_group="O-",
            distance_km=3.5,
            eta_minutes=10,
            eligibility="eligible",
            status="available",
            lat=12.9750,
            lng=77.6000,
        )
        db.add(donor)
        db.commit()

    _create_interaction(db, emergency_id="BL-102", donor_id="D-101", acceptance_status="accepted")

    resp = client.get(
        "/api/v1/emergencies/BL-102/accepted-donors/ranking",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["emergencyId"] == "BL-102"
    assert data["destinationHospitalId"] is not None
    assert data["rankingGeneratedAt"] is not None
    assert data["totalAcceptedDonors"] >= 1
    assert len(data["rankedDonors"]) >= 1

    entry = next((d for d in data["rankedDonors"] if d["donorId"] == "D-101"), None)
    assert entry is not None
    assert entry["acceptanceStatus"] == "accepted"
    assert entry["bloodGroup"] == "O-"
    assert entry["etaAvailable"] is True
    assert entry["estimatedTravelDurationMinutes"] is not None
    assert entry["routeDistanceKm"] is not None
    assert "transitStatusNote" in entry
    assert "physical transit has not begun" in entry["transitStatusNote"]


def test_pending_and_declined_donors_excluded(client, doctor_token, db):
    """Verifies that pending, declined, unreachable, and canceled interactions are strictly excluded."""
    # Add donors
    d_declined = Donor(id="D-TEST-DEC", blood_group="O-", eligibility="eligible", status="declined", lat=12.97, lng=77.59)
    d_pending = Donor(id="D-TEST-PEN", blood_group="O-", eligibility="eligible", status="available", lat=12.97, lng=77.59)
    d_unreach = Donor(id="D-TEST-UNR", blood_group="O-", eligibility="eligible", status="no_response", lat=12.97, lng=77.59)
    d_canceled = Donor(id="D-TEST-CNC", blood_group="O-", eligibility="eligible", status="available", lat=12.97, lng=77.59)
    d_ineligible = Donor(id="D-TEST-INEL", blood_group="O-", eligibility="ineligible", status="accepted", lat=12.97, lng=77.59)
    db.add_all([d_declined, d_pending, d_unreach, d_canceled, d_ineligible])
    db.commit()

    _create_interaction(db, emergency_id="BL-102", donor_id="D-TEST-DEC", acceptance_status="declined")
    _create_interaction(db, emergency_id="BL-102", donor_id="D-TEST-PEN", acceptance_status="pending")
    _create_interaction(db, emergency_id="BL-102", donor_id="D-TEST-UNR", acceptance_status="unreachable")
    _create_interaction(db, emergency_id="BL-102", donor_id="D-TEST-CNC", acceptance_status="accepted", completion_status="canceled")
    _create_interaction(db, emergency_id="BL-102", donor_id="D-TEST-INEL", acceptance_status="accepted")

    resp = client.get(
        "/api/v1/emergencies/BL-102/accepted-donors/ranking",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp.status_code == 200
    ranked_ids = [d["donorId"] for d in resp.json()["rankedDonors"]]

    assert "D-TEST-DEC" not in ranked_ids
    assert "D-TEST-PEN" not in ranked_ids
    assert "D-TEST-UNR" not in ranked_ids
    assert "D-TEST-CNC" not in ranked_ids
    assert "D-TEST-INEL" not in ranked_ids


def test_donors_from_other_emergencies_excluded(client, doctor_token, db):
    """Verifies that accepted donors from another emergency are not included."""
    d_other = Donor(id="D-OTHER-EMG", blood_group="O-", eligibility="eligible", status="accepted", lat=12.98, lng=77.60)
    db.add(d_other)
    db.commit()

    # Link to BL-103 instead of BL-102
    _create_interaction(db, emergency_id="BL-103", donor_id="D-OTHER-EMG", acceptance_status="accepted")

    resp = client.get(
        "/api/v1/emergencies/BL-102/accepted-donors/ranking",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp.status_code == 200
    ranked_ids = [d["donorId"] for d in resp.json()["rankedDonors"]]
    assert "D-OTHER-EMG" not in ranked_ids


def test_duplicate_interactions_deduplicated(client, doctor_token, db):
    """Verifies that multiple accepted interactions for the same donor in the same emergency are deduplicated."""
    d_dup = Donor(id="D-DUP-001", blood_group="O-", eligibility="eligible", status="accepted", lat=12.972, lng=77.595)
    db.add(d_dup)
    db.commit()

    # Insert two accepted interactions for the same donor
    _create_interaction(db, emergency_id="BL-102", donor_id="D-DUP-001", acceptance_status="accepted")
    _create_interaction(db, emergency_id="BL-102", donor_id="D-DUP-001", acceptance_status="accepted")

    resp = client.get(
        "/api/v1/emergencies/BL-102/accepted-donors/ranking",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp.status_code == 200
    ranked_ids = [d["donorId"] for d in resp.json()["rankedDonors"]]
    assert ranked_ids.count("D-DUP-001") == 1


def test_missing_coordinates_handled_safely(client, doctor_token, db):
    """Verifies that donors with missing coordinates are included with unavailable ETA and placed at the end."""
    # Donor with valid coordinates
    d_valid = Donor(id="D-WITH-COORDS", blood_group="O-", eligibility="eligible", status="accepted", lat=12.9716, lng=77.5946)
    # Donor with missing coordinates
    d_missing = Donor(id="D-NO-COORDS", blood_group="O-", eligibility="eligible", status="accepted", lat=None, lng=None)
    db.add_all([d_valid, d_missing])
    db.commit()

    _create_interaction(db, emergency_id="BL-102", donor_id="D-WITH-COORDS", acceptance_status="accepted")
    _create_interaction(db, emergency_id="BL-102", donor_id="D-NO-COORDS", acceptance_status="accepted")

    resp = client.get(
        "/api/v1/emergencies/BL-102/accepted-donors/ranking",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp.status_code == 200
    donors = resp.json()["rankedDonors"]

    entry_missing = next(d for d in donors if d["donorId"] == "D-NO-COORDS")
    assert entry_missing["etaAvailable"] is False
    assert entry_missing["estimatedTravelDurationMinutes"] is None
    assert entry_missing["routeDistanceKm"] is None
    assert entry_missing["etaCalculationMethod"] == "unavailable_missing_coordinates"
    assert entry_missing["isLiveEstimate"] is False

    # The donor with missing coordinates must be ranked after donors with valid ETAs
    valid_idx = next(i for i, d in enumerate(donors) if d["donorId"] == "D-WITH-COORDS")
    missing_idx = next(i for i, d in enumerate(donors) if d["donorId"] == "D-NO-COORDS")
    assert missing_idx > valid_idx


def test_maps_api_fallback_and_live_routing(client, doctor_token, db):
    """Verifies deterministic heuristic fallback and live Google Maps modes."""
    d_geo = Donor(id="D-GEO-TEST", blood_group="O-", eligibility="eligible", status="accepted", lat=12.9500, lng=77.5800)
    db.add(d_geo)
    db.commit()
    _create_interaction(db, emergency_id="BL-102", donor_id="D-GEO-TEST", acceptance_status="accepted")

    # 1. Unconfigured / fallback behavior
    with patch("app.geo.service.settings.GOOGLE_MAPS_API_KEY", ""):
        from app.geo.service import GeospatialService
        with patch("app.services.donor_service.geospatial_service", GeospatialService(api_key="")):
            resp_fallback = client.get(
                "/api/v1/emergencies/BL-102/accepted-donors/ranking",
                headers={"Authorization": f"Bearer {doctor_token}"},
            )
            assert resp_fallback.status_code == 200
            entry = next(d for d in resp_fallback.json()["rankedDonors"] if d["donorId"] == "D-GEO-TEST")
            assert entry["etaCalculationMethod"] == "simulated_heuristic_fallback"
            assert entry["isLiveEstimate"] is False
            assert entry["etaAvailable"] is True
            assert entry["estimatedTravelDurationMinutes"] > 0
            assert entry["routeDistanceKm"] > 0

    # 2. Mocked live Google Maps Distance Matrix response
    mock_maps_response = {
        "status": "OK",
        "rows": [
            {
                "elements": [
                    {
                        "status": "OK",
                        "distance": {"value": 5200, "text": "5.2 km"},
                        "duration": {"value": 780, "text": "13 mins"},
                        "duration_in_traffic": {"value": 660, "text": "11 mins"},
                    }
                ]
            }
        ],
    }

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_maps_response

    async def mock_get(*args, **kwargs):
        return mock_resp

    with patch("app.geo.service.settings.GOOGLE_MAPS_API_KEY", "AIzaSyTestMockKey12345"):
        with patch("httpx.AsyncClient.get", side_effect=mock_get):
            from app.geo.service import GeospatialService
            with patch("app.services.donor_service.geospatial_service", GeospatialService(api_key="AIzaSyTestMockKey12345")):
                resp_live = client.get(
                    "/api/v1/emergencies/BL-102/accepted-donors/ranking",
                    headers={"Authorization": f"Bearer {doctor_token}"},
                )
                assert resp_live.status_code == 200
                entry_live = next(d for d in resp_live.json()["rankedDonors"] if d["donorId"] == "D-GEO-TEST")
                assert entry_live["etaCalculationMethod"] == "google_maps_live"
                assert entry_live["isLiveEstimate"] is True
                assert entry_live["routeDistanceKm"] == 5.2
                assert entry_live["estimatedTravelDurationMinutes"] == 11


def test_missing_and_invalid_emergency_validations(client, doctor_token, db):
    """Verifies that nonexistent, non-blood, or cancelled emergencies are rejected with proper HTTP errors."""
    # 1. Nonexistent emergency ID -> 404
    resp_404 = client.get(
        "/api/v1/emergencies/NONEXISTENT-BL-999/accepted-donors/ranking",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp_404.status_code == 404
    assert "not found" in resp_404.json()["message"].lower()

    # 2. Non-blood emergency (Organ emergency) -> 400
    org_emg = Emergency(
        id="ORG-TEST-999",
        type="organ",
        priority="critical",
        status="active",
        hospital_id="hosp-001",
        hospital_name="City Hospital",
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        description="Kidney transplant",
        organ_type="Kidney",
    )
    db.add(org_emg)
    db.commit()

    resp_non_blood = client.get(
        "/api/v1/emergencies/ORG-TEST-999/accepted-donors/ranking",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp_non_blood.status_code == 400
    assert "blood" in resp_non_blood.json()["message"].lower()

    # 3. Cancelled blood emergency -> 400
    bl_cancelled = Emergency(
        id="BL-TEST-CANCELLED",
        type="blood",
        priority="critical",
        status="cancelled",
        hospital_id="hosp-001",
        hospital_name="City Hospital",
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        description="Cancelled request",
        blood_group="O-",
    )
    db.add(bl_cancelled)
    db.commit()

    resp_cancelled = client.get(
        "/api/v1/emergencies/BL-TEST-CANCELLED/accepted-donors/ranking",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp_cancelled.status_code == 400
    assert "inactive" in resp_cancelled.json()["message"].lower() or "cancelled" in resp_cancelled.json()["message"].lower()


def test_unauthorized_access_protection(client, db, patient_token, donor_token, ambulance_token, coordinator_token, staff_token, admin_token, doctor_token):
    """Verifies that unauthenticated callers, patients, donors, and drivers are forbidden."""
    # 1. Unauthenticated -> 401
    resp_unauth = client.get("/api/v1/emergencies/BL-102/accepted-donors/ranking")
    assert resp_unauth.status_code == 401

    # 2. Patient -> 403
    resp_patient = client.get(
        "/api/v1/emergencies/BL-102/accepted-donors/ranking",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert resp_patient.status_code == 403

    # 3. Donor -> 403
    resp_donor = client.get(
        "/api/v1/emergencies/BL-102/accepted-donors/ranking",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert resp_donor.status_code == 403

    # 4. Ambulance Operator / Driver -> 403
    resp_driver = client.get(
        "/api/v1/emergencies/BL-102/accepted-donors/ranking",
        headers={"Authorization": f"Bearer {ambulance_token}"},
    )
    assert resp_driver.status_code == 403

    # 5. Unverified / pending Doctor -> 403
    unverified_doc = User(
        id="usr-doc-pending-99",
        name="Dr. Unverified",
        email="unverified.doc@hospital.org",
        hashed_password="hash",
        role="doctor",
        is_verified=False,
        verification_status="pending",
        session_status="active",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(unverified_doc)
    db.commit()
    pending_token = create_access_token(subject=unverified_doc.id, role="doctor")

    resp_pending = client.get(
        "/api/v1/emergencies/BL-102/accepted-donors/ranking",
        headers={"Authorization": f"Bearer {pending_token}"},
    )
    assert resp_pending.status_code == 403

    # 6. Authorized Roles -> 200 OK
    for token in [doctor_token, staff_token, admin_token]:
        resp_ok = client.get(
            "/api/v1/emergencies/BL-102/accepted-donors/ranking",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp_ok.status_code == 200


def test_correct_eta_ordering(client, doctor_token, db):
    """Verifies that accepted donors are sorted in strictly ascending order of ETA duration."""
    # Hospital is at (12.9716, 77.5946)
    # Donor Close (~1 km away)
    d_close = Donor(id="D-ORDER-CLOSE", blood_group="O-", eligibility="eligible", status="accepted", lat=12.9750, lng=77.5970)
    # Donor Medium (~4 km away)
    d_medium = Donor(id="D-ORDER-MED", blood_group="O-", eligibility="eligible", status="accepted", lat=12.9900, lng=77.6200)
    # Donor Far (~12 km away)
    d_far = Donor(id="D-ORDER-FAR", blood_group="O-", eligibility="eligible", status="accepted", lat=13.0500, lng=77.6600)
    db.add_all([d_close, d_medium, d_far])
    db.commit()

    _create_interaction(db, emergency_id="BL-102", donor_id="D-ORDER-FAR", acceptance_status="accepted")
    _create_interaction(db, emergency_id="BL-102", donor_id="D-ORDER-CLOSE", acceptance_status="accepted")
    _create_interaction(db, emergency_id="BL-102", donor_id="D-ORDER-MED", acceptance_status="accepted")

    resp = client.get(
        "/api/v1/emergencies/BL-102/accepted-donors/ranking",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp.status_code == 200
    donors = resp.json()["rankedDonors"]

    # Filter to our 3 donors
    test_donors = [d for d in donors if d["donorId"] in ["D-ORDER-CLOSE", "D-ORDER-MED", "D-ORDER-FAR"]]
    assert len(test_donors) == 3

    # Verify strictly sorted: Close < Medium < Far
    assert test_donors[0]["donorId"] == "D-ORDER-CLOSE"
    assert test_donors[1]["donorId"] == "D-ORDER-MED"
    assert test_donors[2]["donorId"] == "D-ORDER-FAR"

    durations = [d["estimatedTravelDurationMinutes"] for d in test_donors]
    assert durations[0] <= durations[1] <= durations[2]


def test_donor_privacy_no_personal_data_leak(client, doctor_token, db):
    """Verifies that donor phone number, raw user ID, or exact coordinates are NOT leaked in response items."""
    d_private = Donor(
        id="D-PRIVACY-001",
        blood_group="O-",
        eligibility="eligible",
        status="accepted",
        lat=12.9716,
        lng=77.5946,
    )
    db.add(d_private)
    db.commit()

    _create_interaction(db, emergency_id="BL-102", donor_id="D-PRIVACY-001", acceptance_status="accepted")

    resp = client.get(
        "/api/v1/emergencies/BL-102/accepted-donors/ranking",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    entry = next(d for d in data["rankedDonors"] if d["donorId"] == "D-PRIVACY-001")

    # Forbidden fields
    assert "phone" not in entry
    assert "lat" not in entry
    assert "lng" not in entry
    assert "coordinates" not in entry
    assert "userId" not in entry
    assert "user_id" not in entry
    assert "medicalLicenseNumber" not in entry

    # Verified safe fields
    assert "donorId" in entry
    assert "bloodGroup" in entry
    assert "acceptanceStatus" in entry
    assert "routeDistanceKm" in entry
    assert "estimatedTravelDurationMinutes" in entry
    assert "transitStatusNote" in entry
    assert "transit has not begun" in entry["transitStatusNote"]
