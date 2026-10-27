"""
LifeLink Phase 2 — Verified Donor Response Workflow & Safeguard Tests
File: backend/tests/test_donor_response_workflow.py

Validates:
1. Successful donor acceptance via interaction endpoint (real latency, status, location consent).
2. Successful donor decline with rejection reason.
3. Cross-donor authorization guard: Donor A cannot accept an interaction belonging to Donor B (HTTP 403).
4. Repeated submission prevention: Submitting a second response returns HTTP 400.
5. State transition integrity: Cannot record response for unattempted interaction (HTTP 400).
6. Role-based access control: Patient role is forbidden from submitting donor response (HTTP 403).
7. Unauthenticated request rejection: Missing token returns HTTP 401.
8. Cross-donor tampering protection on /api/v1/blood/donors/{donor_id}/response (HTTP 403).
9. Repeated submission rejection on /api/v1/blood/donors/{donor_id}/response (HTTP 400).
10. Synthetic donor safeguards remain active (HTTP 403 on contact attempt).
"""

import pytest
from app.models.donor import Donor
from app.models.interaction import DonorEmergencyInteraction
from app.models.audit import AuditLog


def test_donor_accept_own_interaction_success(client, doctor_token, donor_token, db):
    # 1. Candidate selection by doctor
    res_sel = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    assert res_sel.status_code == 201
    int_id = res_sel.json()["id"]

    # 2. Contact attempt by dispatcher
    res_att = client.post(
        f"/api/v1/blood/interactions/{int_id}/attempt",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"contactChannel": "sms"},
    )
    assert res_att.status_code == 200

    # 3. Donor submits acceptance for own interaction
    res_resp = client.post(
        f"/api/v1/blood/interactions/{int_id}/response",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"accepted": True, "shareLocation": True, "notes": "Accepted via Donor Participation Portal"},
    )
    assert res_resp.status_code == 200
    data = res_resp.json()
    assert data["responseStatus"] == "responded"
    assert data["acceptanceStatus"] == "accepted"
    assert data["respondedAt"] is not None
    assert data["responseLatencySeconds"] is not None
    assert data["responseLatencySeconds"] >= 0

    # Verify donor model updated
    donor = db.query(Donor).filter(Donor.id == "D-101").first()
    assert donor.status == "accepted"
    assert donor.location_consent_granted is True

    # Verify audit log recorded
    audit = db.query(AuditLog).filter(
        AuditLog.resource_id == int_id,
        AuditLog.action.contains("Response logged"),
    ).first()
    assert audit is not None
    assert audit.status == "success"
    assert audit.actor_type == "donor"


def test_donor_decline_own_interaction_success(client, doctor_token, donor_token, db):
    # Candidate selection & attempt
    res_sel = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    assert res_sel.status_code == 201
    int_id = res_sel.json()["id"]

    client.post(
        f"/api/v1/blood/interactions/{int_id}/attempt",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"contactChannel": "sms"},
    )

    # Donor declines
    res_resp = client.post(
        f"/api/v1/blood/interactions/{int_id}/response",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"accepted": False, "rejectionReason": "Temporarily unavailable"},
    )
    assert res_resp.status_code == 200
    data = res_resp.json()
    assert data["responseStatus"] == "responded"
    assert data["acceptanceStatus"] == "declined"
    assert data["rejectionReason"] == "Temporarily unavailable"

    # Verify donor model updated
    donor = db.query(Donor).filter(Donor.id == "D-101").first()
    assert donor.status == "declined"


def test_donor_cannot_respond_to_another_donors_interaction(client, doctor_token, donor_token):
    # Create candidate interaction for D-102 (belongs to another user: usr-dnr-006)
    res_sel = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-102"},
    )
    assert res_sel.status_code == 201
    d102_int_id = res_sel.json()["id"]

    client.post(
        f"/api/v1/blood/interactions/{d102_int_id}/attempt",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"contactChannel": "sms"},
    )

    # donor_token belongs to usr-dnr-005 (Donor D-101).
    # Attempting to respond to D-102's interaction must be rejected with HTTP 403.
    res_forbidden = client.post(
        f"/api/v1/blood/interactions/{d102_int_id}/response",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"accepted": True},
    )
    assert res_forbidden.status_code == 403
    assert "own interaction requests" in (res_forbidden.json().get("message") or res_forbidden.json().get("detail", ""))


def test_donor_repeated_submission_rejected(client, doctor_token, donor_token):
    # Candidate selection & attempt
    res_sel = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    int_id = res_sel.json()["id"]

    client.post(
        f"/api/v1/blood/interactions/{int_id}/attempt",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"contactChannel": "sms"},
    )

    # First response: succeeds
    res1 = client.post(
        f"/api/v1/blood/interactions/{int_id}/response",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"accepted": True},
    )
    assert res1.status_code == 200

    # Second response on same interaction: rejected
    res2 = client.post(
        f"/api/v1/blood/interactions/{int_id}/response",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"accepted": False},
    )
    assert res2.status_code == 400
    assert "already been recorded" in (res2.json().get("message") or res2.json().get("detail", ""))


def test_unattempted_interaction_response_rejected(client, doctor_token, donor_token):
    # Candidate selection only (not attempted)
    res_sel = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    int_id = res_sel.json()["id"]

    # Attempting to respond before contact attempt must return HTTP 400
    res_invalid = client.post(
        f"/api/v1/blood/interactions/{int_id}/response",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"accepted": True},
    )
    assert res_invalid.status_code == 400
    assert "unattempted" in (res_invalid.json().get("message") or res_invalid.json().get("detail", ""))


def test_patient_cannot_submit_donor_response(client, doctor_token, patient_token):
    res_sel = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    int_id = res_sel.json()["id"]

    client.post(
        f"/api/v1/blood/interactions/{int_id}/attempt",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"contactChannel": "sms"},
    )

    # Patient role is forbidden from interaction response
    res_forbid = client.post(
        f"/api/v1/blood/interactions/{int_id}/response",
        headers={"Authorization": f"Bearer {patient_token}"},
        json={"accepted": True},
    )
    assert res_forbid.status_code == 403


def test_unauthenticated_interaction_response_rejected(client, doctor_token):
    res_sel = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    int_id = res_sel.json()["id"]

    # Missing authorization header returns 401
    res_unauth = client.post(
        f"/api/v1/blood/interactions/{int_id}/response",
        json={"accepted": True},
    )
    assert res_unauth.status_code == 401


def test_blood_endpoint_cross_donor_tampering_blocked(client, donor_token):
    # donor_token belongs to usr-dnr-005 (Donor D-101).
    # Attempting to respond to D-102 (belongs to usr-dnr-006) returns HTTP 403.
    res_tamper = client.post(
        "/api/v1/blood/donors/D-102/response",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"status": "accepted", "shareLocation": True},
    )
    assert res_tamper.status_code == 403
    assert "own profile" in (res_tamper.json().get("message") or res_tamper.json().get("detail", ""))


def test_blood_endpoint_repeated_submission_rejected(client, donor_token, db):
    # Ensure D-101 is reset to contacted
    donor = db.query(Donor).filter(Donor.id == "D-101").first()
    donor.status = "contacted"
    db.commit()

    headers = {"Authorization": f"Bearer {donor_token}"}
    # First response succeeds
    res1 = client.post(
        "/api/v1/blood/donors/D-101/response",
        headers=headers,
        json={"status": "accepted", "shareLocation": True},
    )
    assert res1.status_code == 200

    # Repeated submission with same status returns 400
    res2 = client.post(
        "/api/v1/blood/donors/D-101/response",
        headers=headers,
        json={"status": "accepted", "shareLocation": True},
    )
    assert res2.status_code == 400
    assert "already been recorded" in (res2.json().get("message") or res2.json().get("detail", ""))


def test_synthetic_donor_contact_blocked(client, doctor_token, db):
    # Ensure synthetic benchmark profile exists
    synth = db.query(Donor).filter(Donor.id == "D-SYNTH-01").first()
    if not synth:
        synth = Donor(
            id="D-SYNTH-01",
            blood_group="O+",
            lat=12.9716,
            lng=77.5946,
            is_synthetic=True,
            data_provenance="synthetic_registry",
            status="available",
        )
        db.add(synth)
        db.commit()

    # Attempting to contact synthetic benchmark profile returns HTTP 403
    res_contact = client.post(
        "/api/v1/blood/donors/D-SYNTH-01/contact",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102"},
    )
    assert res_contact.status_code == 403
    assert "synthetic benchmark profile" in (res_contact.json().get("message") or res_contact.json().get("detail", ""))


def test_donor_response_omitted_share_location_does_not_grant_location_consent(client, donor_token, db):
    """
    Verifies that when a donor responds with accepted=True but omits shareLocation,
    location consent is NOT silently granted (location_consent_granted remains False).
    """
    from app.models.donor import Donor
    from app.models.interaction import DonorEmergencyInteraction

    donor = db.query(Donor).filter(Donor.id == "D-101").first()
    donor.status = "contacted"
    donor.location_consent_granted = False
    db.commit()

    # Find or create active interaction for D-101
    interaction = db.query(DonorEmergencyInteraction).filter(
        DonorEmergencyInteraction.donor_id == "D-101",
        DonorEmergencyInteraction.completion_status == "pending",
    ).first()
    if not interaction:
        interaction = DonorEmergencyInteraction(
            id="dint-consent-test-01",
            emergency_id="BL-102",
            donor_id="D-101",
            selected_at="2026-10-18T10:00:00Z",
            distance_km=2.5,
            eta_minutes=8,
            time_of_day_hours=10.0,
            day_of_week=0,
            emergency_priority="critical",
            contact_status="attempted",
            response_status="pending",
            acceptance_status="pending",
            completion_status="pending",
            data_provenance="production",
            is_synthetic=False,
            created_at="2026-10-18T10:00:00Z",
            updated_at="2026-10-18T10:00:00Z",
        )
        db.add(interaction)
        db.commit()

    # Donor responds via interaction endpoint omitting shareLocation
    response = client.post(
        f"/api/v1/blood/interactions/{interaction.id}/response",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"accepted": True, "notes": "Responding without location share"},
    )
    assert response.status_code == 200

    # Verify donor status transitioned to accepted, but location consent was NOT granted
    db.refresh(donor)
    assert donor.status == "accepted"
    assert donor.location_consent_granted is False

