"""End-to-End Integration Verification: Complete Blood Emergency Workflow.
Section 5 Requirements:
Doctor creates blood emergency
  -> authorized donor workflow identifies eligible donors
  -> donor response is recorded
  -> ambulance status is updated through supported functionality
  -> admin reviews the corresponding audit trail.
All executed strictly against in-memory isolated database.
"""
import pytest
from app.models.donor import Donor
from app.models.consent import Consent
from app.models.ambulance import Ambulance
from app.models.audit import AuditLog
from app.simulation.mock_notifications import mock_notification_provider


def test_complete_blood_emergency_workflow_e2e(
    client, doctor_token, donor_token, ambulance_token, admin_token, patient_token, db
):
    # Step 0: Ensure mock notification provider is clean
    mock_notification_provider.clear()
    initial_notifs = mock_notification_provider.count()

    # -------------------------------------------------------------------------
    # STEP 1: Doctor creates blood emergency
    # -------------------------------------------------------------------------
    emg_payload = {
        "type": "blood",
        "priority": "critical",
        "hospitalId": "city-hospital-001",
        "description": "Urgent O- blood transfusion for trauma patient",
        "bloodGroup": "O-",
        "unitsRequired": 2,
    }
    res_create = client.post(
        "/api/v1/emergencies",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json=emg_payload,
    )
    assert res_create.status_code == 200, f"Emergency creation failed: {res_create.text}"
    emg_data = res_create.json()
    emergency_id = emg_data["id"]
    assert emergency_id is not None
    assert emg_data["status"] == "created"
    assert emg_data.get("bloodGroup") == "O-" or emg_data.get("bloodType") == "O-"

    # -------------------------------------------------------------------------
    # STEP 2: Authorized donor workflow identifies eligible donors
    # -------------------------------------------------------------------------
    res_donors = client.get(
        "/api/v1/donors",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert res_donors.status_code == 200
    donors = res_donors.json()
    assert len(donors) >= 1

    # Find an eligible donor with O- blood group
    eligible_donor = next((d for d in donors if d["bloodGroup"] == "O-"), donors[0])
    donor_id = eligible_donor["id"]

    # -------------------------------------------------------------------------
    # STEP 3: Safeguard verification - Synthetic donors blocked from live dispatch
    # -------------------------------------------------------------------------
    # Check if a synthetic donor exists or mark one to verify guard
    synth_donor = db.query(Donor).filter(Donor.is_synthetic == True).first()
    if synth_donor:
        res_synth = client.post(
            f"/api/v1/blood/donors/{synth_donor.id}/contact",
            headers={"Authorization": f"Bearer {doctor_token}"},
            json={"emergencyId": emergency_id},
        )
        assert res_synth.status_code == 403
        assert "synthetic" in res_synth.text.lower()

    # -------------------------------------------------------------------------
    # STEP 4: Doctor contacts eligible consented donor
    # -------------------------------------------------------------------------
    # Ensure donor has affirmative communication consent
    donor_db = db.query(Donor).filter(Donor.id == donor_id).first()
    assert donor_db is not None
    if donor_db.user_id:
        consent = db.query(Consent).filter(Consent.user_id == donor_db.user_id).first()
        if consent:
            consent.emergency_communication = True
            db.commit()

    # Reset status to eligible if needed for test
    donor_db.status = "eligible"
    donor_db.eligibility = "eligible"
    db.commit()

    res_contact = client.post(
        f"/api/v1/blood/donors/{donor_id}/contact",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": emergency_id},
    )
    assert res_contact.status_code == 200, f"Contact donor failed: {res_contact.text}"
    contact_data = res_contact.json()
    assert contact_data["status"] == "contacted"
    assert contact_data["donorId"] == donor_id

    # Verify mock notification recorded (no live SMS sent)
    assert mock_notification_provider.count() > initial_notifs
    latest_record = mock_notification_provider.get_records()[-1]
    assert latest_record.status == "mock_delivered"
    assert donor_id in latest_record.metadata.get("donor_id", "")

    # -------------------------------------------------------------------------
    # STEP 5: Donor records response (Accepts SOS with location consent)
    # -------------------------------------------------------------------------
    res_response = client.post(
        f"/api/v1/blood/donors/{donor_id}/response",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"status": "accepted", "shareLocation": True},
    )
    assert res_response.status_code == 200, f"Donor response failed: {res_response.text}"
    response_data = res_response.json()
    assert response_data["status"] == "accepted"

    # Verify donor model updated in DB
    db.refresh(donor_db)
    assert donor_db.status == "accepted"
    assert donor_db.location_consent_granted is True

    # -------------------------------------------------------------------------
    # STEP 6: Ambulance status and location updated through supported functionality
    # -------------------------------------------------------------------------
    res_amb_status = client.post(
        "/api/v1/ambulances/amb-042/status",
        headers={"Authorization": f"Bearer {ambulance_token}"},
        json={"status": "dispatched", "notes": f"Dispatched for Blood Emergency {emergency_id}"},
    )
    assert res_amb_status.status_code == 200, f"Ambulance status update failed: {res_amb_status.text}"
    amb_data = res_amb_status.json()
    assert amb_data["status"] == "dispatched"

    res_amb_loc = client.post(
        "/api/v1/ambulances/amb-042/location",
        headers={"Authorization": f"Bearer {ambulance_token}"},
        json={"lat": 12.9750, "lng": 77.5990, "speedKmh": 52.0, "heading": 180.0},
    )
    assert res_amb_loc.status_code == 200
    loc_data = res_amb_loc.json()
    assert loc_data["currentLocation"]["lat"] == 12.9750

    # Verify ambulance DB persistence
    amb_db = db.query(Ambulance).filter(Ambulance.id == "amb-042").first()
    assert amb_db.status == "dispatched"
    assert amb_db.lat == 12.9750

    # -------------------------------------------------------------------------
    # STEP 7: Admin reviews audit trail
    # -------------------------------------------------------------------------
    res_audit = client.get(
        "/api/v1/audit",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_audit.status_code == 200, f"Admin audit fetch failed: {res_audit.text}"
    audit_logs = res_audit.json()
    assert isinstance(audit_logs, list)
    assert len(audit_logs) >= 3

    # Check for presence of actions in audit logs
    actions = [log.get("action", "") for log in audit_logs]
    has_donor_audit = any(donor_id in act for act in actions)
    has_amb_audit = any("amb-042" in act.lower() or "ambulance" in act.lower() for act in actions)
    assert has_donor_audit, f"Donor audit record not found in: {actions[:5]}"
    assert has_amb_audit, f"Ambulance audit record not found in: {actions[:5]}"

    # -------------------------------------------------------------------------
    # STEP 8: RBAC Verification - Unauthorized roles denied audit view
    # -------------------------------------------------------------------------
    res_unauth_audit = client.get(
        "/api/v1/audit",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert res_unauth_audit.status_code == 403, "Patient must be denied access to audit logs"
