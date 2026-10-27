import pytest
from app.models.consent import Consent
from app.models.donor import Donor
from app.models.emergency import Emergency
from app.models.interaction import DonorEmergencyInteraction
from app.models.audit import AuditLog
from app.core.security import create_access_token


def test_valid_candidate_selection_event(client, doctor_token):
    # Candidate selection captures immutable features at dispatch time
    response = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={
            "emergencyId": "BL-102",
            "donorId": "D-101",
            "compatibilityMatchType": "identical",
            "isSynthetic": False,
            "dataProvenance": "production",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["emergencyId"] == "BL-102"
    assert data["donorId"] == "D-101"
    assert data["distanceKm"] > 0
    assert data["etaMinutes"] > 0
    assert 0.0 <= data["timeOfDayHours"] <= 24.0
    assert 0 <= data["dayOfWeek"] <= 6
    assert data["emergencyPriority"] == "critical"
    assert data["compatibilityMatchType"] == "identical"
    assert data["donorAvailabilityAtSelection"] == "available"
    # All outcome states initialized strictly to pending (not negative/false)
    assert data["contactStatus"] == "pending"
    assert data["responseStatus"] == "pending"
    assert data["acceptanceStatus"] == "pending"
    assert data["completionStatus"] == "pending"
    assert data["isSynthetic"] is False
    assert data["dataProvenance"] == "production"


def test_candidate_selection_missing_emergency(client, doctor_token):
    response = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={
            "emergencyId": "NONEXISTENT-EMERGENCY",
            "donorId": "D-101",
        },
    )
    assert response.status_code == 404
    assert "not found" in response.json()["message"]


def test_candidate_selection_missing_donor(client, doctor_token):
    response = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={
            "emergencyId": "BL-102",
            "donorId": "D-NONEXISTENT",
        },
    )
    assert response.status_code == 404
    assert "not found" in response.json()["message"]


def test_candidate_selection_ineligible_donor_blocked(client, doctor_token):
    # D-103 is seeded as ineligible in init_db
    response = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={
            "emergencyId": "BL-102",
            "donorId": "D-103",
        },
    )
    assert response.status_code == 400
    assert "ineligible" in response.json()["message"]


def test_invalid_role_access(client, patient_token, donor_token):
    # Patients cannot record candidate selections
    res_patient = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {patient_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    assert res_patient.status_code == 403

    # Donors cannot record candidate selections
    res_donor = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    assert res_donor.status_code == 403


def test_complete_interaction_lifecycle_and_state_transitions(client, doctor_token, donor_token):
    # 1. Candidate Selection
    res_sel = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    assert res_sel.status_code == 201
    interaction_id = res_sel.json()["id"]

    # INVALID TRANSITION: Cannot record delivery or response before attempt
    res_invalid_del = client.post(
        f"/api/v1/blood/interactions/{interaction_id}/delivered",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={},
    )
    assert res_invalid_del.status_code == 400

    res_invalid_resp = client.post(
        f"/api/v1/blood/interactions/{interaction_id}/response",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"accepted": True},
    )
    assert res_invalid_resp.status_code == 400

    # 2. Contact Attempt
    res_att = client.post(
        f"/api/v1/blood/interactions/{interaction_id}/attempt",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"contactChannel": "sms"},
    )
    assert res_att.status_code == 200
    assert res_att.json()["contactStatus"] == "attempted"
    assert res_att.json()["contactAttemptedAt"] is not None

    # 3. Contact Delivery Receipt
    res_del = client.post(
        f"/api/v1/blood/interactions/{interaction_id}/delivered",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"outcomeSource": "telephony_webhook"},
    )
    assert res_del.status_code == 200
    assert res_del.json()["contactStatus"] == "delivered"
    assert res_del.json()["contactDeliveredAt"] is not None

    # INVALID TRANSITION: Cannot complete donation before response
    res_invalid_comp = client.post(
        f"/api/v1/blood/interactions/{interaction_id}/complete",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"completionStatus": "completed", "unitsDonated": 1},
    )
    assert res_invalid_comp.status_code == 400

    # 4. Donor Response (D-101's assigned user submitting response)
    res_resp = client.post(
        f"/api/v1/blood/interactions/{interaction_id}/response",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"accepted": True, "notes": "En route to hospital"},
    )
    assert res_resp.status_code == 200
    resp_data = res_resp.json()
    assert resp_data["responseStatus"] == "responded"
    assert resp_data["acceptanceStatus"] == "accepted"
    assert resp_data["respondedAt"] is not None
    assert resp_data["responseLatencySeconds"] is not None
    assert resp_data["responseLatencySeconds"] >= 0

    # INVALID TRANSITION: Cannot record response a second time
    res_second_resp = client.post(
        f"/api/v1/blood/interactions/{interaction_id}/response",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"accepted": False},
    )
    assert res_second_resp.status_code == 400

    # 5. Verified Donation Completion at Hospital
    res_comp = client.post(
        f"/api/v1/blood/interactions/{interaction_id}/complete",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"completionStatus": "completed", "unitsDonated": 1},
    )
    assert res_comp.status_code == 200
    comp_data = res_comp.json()
    assert comp_data["completionStatus"] == "completed"
    assert comp_data["unitsDonated"] == 1
    assert comp_data["completedAt"] is not None


def test_pending_vs_negative_outcome_semantics(client, doctor_token):
    # Candidate selected without contact must remain pending, NOT failed/rejected
    res_sel = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-102"},
    )
    assert res_sel.status_code == 201
    interaction_id = res_sel.json()["id"]

    # Contact attempted without response
    res_att = client.post(
        f"/api/v1/blood/interactions/{interaction_id}/attempt",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"contactChannel": "push"},
    )
    assert res_att.status_code == 200
    data = res_att.json()

    # Crucial semantic rule: unresponded does NOT equal declined or failed
    assert data["responseStatus"] == "pending"
    assert data["acceptanceStatus"] == "pending"
    assert data["completionStatus"] == "pending"
    assert data["rejectionReason"] is None


def test_duplicate_candidate_handling(client, doctor_token):
    # Selecting the same donor twice while pending returns existing interaction
    res1 = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    assert res1.status_code == 201
    id1 = res1.json()["id"]

    res2 = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    assert res2.status_code == 201
    id2 = res2.json()["id"]
    assert id1 == id2


def test_donor_privacy_boundary(client, doctor_token, donor_token, db):
    # Create an interaction for D-102 (belongs to another donor user: usr-dnr-006)
    res = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-102"},
    )
    d102_int_id = res.json()["id"]

    # donor_token belongs to usr-dnr-005 (Donor D-101)
    # Accessing D-102's interaction must return 403 Forbidden
    res_forbidden = client.get(
        f"/api/v1/blood/interactions/{d102_int_id}",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert res_forbidden.status_code == 403

    # Listing interactions as a donor returns ONLY records where donor_id is their own
    list_res = client.get(
        "/api/v1/blood/interactions",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    for item in items:
        assert item["donorId"] == "D-101"


def test_consent_boundary_blocks_contact_attempt(client, doctor_token, db):
    # Create candidate
    res = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    interaction_id = res.json()["id"]

    # Revoke emergency communication consent for D-101
    consent = db.query(Consent).filter(Consent.user_id == "usr-dnr-005").first()
    assert consent is not None
    consent.emergency_communication = False
    db.commit()

    # Attempting contact must be blocked by consent policy
    att_res = client.post(
        f"/api/v1/blood/interactions/{interaction_id}/attempt",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"contactChannel": "sms"},
    )
    assert att_res.status_code == 403
    assert "emergency communication consent" in att_res.json()["message"]


def test_audit_logging_and_synthetic_provenance(client, doctor_token, db):
    # Record synthetic benchmark fixture
    res = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={
            "emergencyId": "BL-102",
            "donorId": "D-101",
            "isSynthetic": True,
            "dataProvenance": "synthetic_simulation",
            "notes": "Simulated ML benchmark fixture",
        },
    )
    assert res.status_code == 201
    int_id = res.json()["id"]

    # Verify audit log exists
    audit_entry = db.query(AuditLog).filter(
        AuditLog.resource_id == int_id,
        AuditLog.status == "success",
    ).first()
    assert audit_entry is not None
    assert "Candidate donor" in audit_entry.action

    # Query with provenance filter
    res_synth = client.get(
        "/api/v1/blood/interactions?isSynthetic=true",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert res_synth.status_code == 200
    items = res_synth.json()["items"]
    assert any(i["id"] == int_id and i["isSynthetic"] is True for i in items)


def test_contact_failure_lifecycle(client, doctor_token):
    # Candidate selection
    res_sel = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    assert res_sel.status_code == 201
    int_id = res_sel.json()["id"]

    # Record contact attempt
    client.post(
        f"/api/v1/blood/interactions/{int_id}/attempt",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"contactChannel": "sms"},
    )

    # Carrier failure occurs
    res_fail = client.post(
        f"/api/v1/blood/interactions/{int_id}/failed",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"failureReason": "Carrier unreachable / invalid routing", "notes": "Telephony error 30008"},
    )
    assert res_fail.status_code == 200
    data = res_fail.json()
    assert data["contactStatus"] == "failed"
    assert "Carrier unreachable" in data["notes"]


def test_contact_timeout_and_unreachable_semantics(client, doctor_token):
    # Candidate selection
    res_sel = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    assert res_sel.status_code == 201
    int_id = res_sel.json()["id"]

    # Attempt contact
    client.post(
        f"/api/v1/blood/interactions/{int_id}/attempt",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"contactChannel": "push"},
    )

    # Cannot time out uncontacted interaction
    # But now it is contacted, so timeout window elapses
    res_tout = client.post(
        f"/api/v1/blood/interactions/{int_id}/timeout",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"timeoutReason": "15-minute response window expired without donor acknowledgement"},
    )
    assert res_tout.status_code == 200
    data = res_tout.json()
    assert data["responseStatus"] == "no_response"
    assert data["acceptanceStatus"] == "unreachable"
    # Latency must remain None (unobserved)
    assert data["responseLatencySeconds"] is None

    # Cannot time out again if already resolved
    res_repeat = client.post(
        f"/api/v1/blood/interactions/{int_id}/timeout",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={},
    )
    assert res_repeat.status_code == 200  # Idempotent


def test_interaction_cancellation_lifecycle(client, doctor_token):
    # Candidate selection
    res_sel = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    assert res_sel.status_code == 201
    int_id = res_sel.json()["id"]

    # Emergency is resolved elsewhere, so candidate interaction is cancelled
    res_cnc = client.post(
        f"/api/v1/blood/interactions/{int_id}/cancel",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"cancellationReason": "Blood units secured from internal blood bank stock"},
    )
    assert res_cnc.status_code == 200
    data = res_cnc.json()
    assert data["completionStatus"] == "canceled"
    assert "Blood units secured" in data["notes"]


def test_donor_service_contact_and_response_synchronization(client, doctor_token, donor_token, db):
    # Calling legacy contact_donor endpoint automatically logs production interaction
    res_contact = client.post(
        "/api/v1/blood/donors/D-101/contact",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102"},
    )
    assert res_contact.status_code == 200

    # Verify interaction ledger synchronized
    int_record = db.query(DonorEmergencyInteraction).filter(
        DonorEmergencyInteraction.emergency_id == "BL-102",
        DonorEmergencyInteraction.donor_id == "D-101",
    ).first()
    assert int_record is not None
    assert int_record.contact_status == "attempted"
    assert int_record.contact_attempted_at is not None
    assert int_record.response_status == "pending"

    # Donor records response
    res_resp = client.post(
        "/api/v1/blood/donors/D-101/response",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"status": "accepted", "shareLocation": True},
    )
    assert res_resp.status_code == 200

    # Reload interaction and verify response synchronized
    db.refresh(int_record)
    assert int_record.response_status == "responded"
    assert int_record.acceptance_status == "accepted"
    assert int_record.responded_at is not None
