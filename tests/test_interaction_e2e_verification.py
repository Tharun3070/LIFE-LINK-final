import pytest
from datetime import datetime, timezone
from app.models.consent import Consent
from app.models.donor import Donor
from app.models.emergency import Emergency
from app.models.interaction import DonorEmergencyInteraction
from app.models.audit import AuditLog
from app.services.ml_audit_service import MLAuditService
from app.core.security import create_access_token


def test_e2e_contact_attempt_creates_or_reuses_interaction_and_deduplicates(client, doctor_token, db):
    """
    Verifies that:
    1. Candidate selection creates a new interaction record.
    2. Repeated selection of the same (emergency, donor) pair reuses the existing active record.
    3. Operational dispatch (/blood/donors/{id}/contact) reuses and synchronizes the active record without creating duplicates.
    """
    initial_count = db.query(DonorEmergencyInteraction).count()

    # Step 1: Select candidate
    res_sel1 = client.post(
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
    assert res_sel1.status_code == 201
    int_id_1 = res_sel1.json()["id"]
    assert db.query(DonorEmergencyInteraction).count() == initial_count + 1

    # Step 2: Repeated candidate selection for same pair must reuse existing active interaction
    res_sel2 = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={
            "emergencyId": "BL-102",
            "donorId": "D-101",
        },
    )
    assert res_sel2.status_code == 201
    assert res_sel2.json()["id"] == int_id_1
    # Count must remain exactly initial_count + 1 (no duplicate active rows created)
    assert db.query(DonorEmergencyInteraction).count() == initial_count + 1

    # Step 3: Record contact attempt
    res_att = client.post(
        f"/api/v1/blood/interactions/{int_id_1}/attempt",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"contactChannel": "sms"},
    )
    assert res_att.status_code == 200
    assert res_att.json()["contactStatus"] == "attempted"
    assert res_att.json()["contactAttemptedAt"] is not None

    # Step 4: Dispatch via operational endpoint reuses the same interaction
    res_contact = client.post(
        "/api/v1/blood/donors/D-101/contact",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102"},
    )
    assert res_contact.status_code == 200
    # Must NOT have created an additional active interaction row
    assert db.query(DonorEmergencyInteraction).count() == initial_count + 1


def test_e2e_response_updates_correct_record_and_calculates_latency(client, doctor_token, donor_token, db):
    """
    Verifies that:
    1. A donor response updates the existing active interaction record.
    2. Response latency is calculated only from the valid contact attempt timestamp.
    3. Conflicting multiple responses are rejected.
    """
    # Create candidate and attempt contact
    res_sel = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    int_id = res_sel.json()["id"]

    client.post(
        f"/api/v1/blood/interactions/{int_id}/attempt",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"contactChannel": "push"},
    )

    # Donor records response
    res_resp = client.post(
        f"/api/v1/blood/interactions/{int_id}/response",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"accepted": True, "outcomeSource": "donor_app"},
    )
    assert res_resp.status_code == 200
    data = res_resp.json()
    assert data["responseStatus"] == "responded"
    assert data["acceptanceStatus"] == "accepted"
    assert data["respondedAt"] is not None
    # Latency must be non-negative integer calculated from attempted_at to responded_at
    assert data["responseLatencySeconds"] is not None
    assert data["responseLatencySeconds"] >= 0

    # Repeat response attempt must be rejected (cannot conflict with already recorded response)
    res_repeat = client.post(
        f"/api/v1/blood/interactions/{int_id}/response",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"accepted": False, "rejectionReason": "Changed mind"},
    )
    assert res_repeat.status_code == 400
    assert "already been recorded" in res_repeat.json()["message"]


def test_e2e_pending_is_not_counted_as_negative_outcome(client, doctor_token, donor_token, db):
    """
    Verifies that pending interactions are not treated as negative outcomes in ML audit metrics.
    """
    # 1. Create interaction 1: Contact attempted, but donor is still pending response
    res1 = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    int_id_1 = res1.json()["id"]
    client.post(
        f"/api/v1/blood/interactions/{int_id_1}/attempt",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"contactChannel": "sms"},
    )

    # 2. Create interaction 2 for a different donor: Contact attempted, donor accepted
    # Set up D-102 with consent
    d102 = db.query(Donor).filter(Donor.id == "D-102").first()
    d102.eligibility = "eligible"
    d102.status = "available"
    consent102 = Consent(
        id="c-d102",
        user_id="usr-stf-002",
        emergency_communication=True,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(consent102)
    d102.user_id = "usr-stf-002"
    db.commit()

    res2 = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-102"},
    )
    int_id_2 = res2.json()["id"]
    client.post(
        f"/api/v1/blood/interactions/{int_id_2}/attempt",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"contactChannel": "sms"},
    )
    res_resp = client.post(
        f"/api/v1/blood/interactions/{int_id_2}/response",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"accepted": True, "outcomeSource": "dispatcher_portal"},
    )
    assert res_resp.status_code == 200

    # Step 3: Run MLAuditService on db
    report = MLAuditService.audit_interactions(db)

    # Total interactions = 2 (1 pending, 1 responded/accepted)
    assert report["volume"]["total_interactions"] == 2

    # Target A evaluates Response Propensity P(Response | Dispatch Attempt)
    # The pending interaction must NOT be counted as a negative (non-response)
    target_a = report["prediction_targets"]["target_a_response_propensity"]
    assert target_a["eligible_records"] == 1
    assert target_a["positive_count (responded)"] == 1
    assert target_a["negative_count (no_response/expired)"] == 0
    # Positive ratio must be 1.0 (1 responded out of 1 resolved), NOT 0.5 (which would happen if pending were treated as negative)
    assert target_a["positive_ratio"] == 1.0


def test_e2e_unobserved_timeout_does_not_fabricate_latency(client, doctor_token, db):
    """
    Verifies that timeout events do not fabricate latency or response timestamps.
    """
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

    res_tout = client.post(
        f"/api/v1/blood/interactions/{int_id}/timeout",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"timeoutReason": "15-minute response window expired"},
    )
    assert res_tout.status_code == 200
    data = res_tout.json()
    assert data["responseStatus"] == "no_response"
    assert data["acceptanceStatus"] == "unreachable"
    # Latency must remain None
    assert data["responseLatencySeconds"] is None
    assert data["respondedAt"] is None

    # Audit must report 0 negative latencies and pass data integrity checks
    report = MLAuditService.audit_interactions(db)
    assert report["data_integrity"]["negative_latencies"] == 0
    assert report["data_integrity"]["missing_response_timestamps"] == 0
    assert report["data_integrity"]["passed_integrity_checks"] is True


def test_e2e_synthetic_records_strictly_excluded_from_training_targets(client, doctor_token, db):
    """
    Verifies that synthetic benchmark interactions are separated from production records
    and excluded from ML target eligibility.
    """
    # 1. Create a production interaction
    res_prod = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={
            "emergencyId": "BL-102",
            "donorId": "D-101",
            "isSynthetic": False,
            "dataProvenance": "production",
        },
    )
    int_prod_id = res_prod.json()["id"]
    client.post(f"/api/v1/blood/interactions/{int_prod_id}/attempt", headers={"Authorization": f"Bearer {doctor_token}"}, json={"contactChannel": "sms"})
    client.post(f"/api/v1/blood/interactions/{int_prod_id}/response", headers={"Authorization": f"Bearer {doctor_token}"}, json={"accepted": True})

    # 2. Create a synthetic benchmark interaction
    synth_int = DonorEmergencyInteraction(
        id="dint-synth-001",
        emergency_id="BL-102",
        donor_id="D-101",
        selected_at=datetime.now(timezone.utc).isoformat(),
        distance_km=4.5,
        eta_minutes=12,
        time_of_day_hours=14.0,
        day_of_week=2,
        emergency_priority="critical",
        compatibility_match_type="identical",
        donor_availability_at_selection="available",
        contact_status="attempted",
        contact_channel="sms",
        contact_attempted_at=datetime.now(timezone.utc).isoformat(),
        response_status="responded",
        responded_at=datetime.now(timezone.utc).isoformat(),
        response_latency_seconds=120,
        acceptance_status="accepted",
        completion_status="completed",
        is_synthetic=True,
        data_provenance="synthetic_benchmark",
        outcome_source="simulation",
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(synth_int)
    db.commit()

    report = MLAuditService.audit_interactions(db)
    assert report["volume"]["total_interactions"] == 2
    assert report["provenance"]["production_records"] == 1
    assert report["provenance"]["synthetic_records"] == 1

    # Target A, B, C must strictly count only the 1 production record
    assert report["prediction_targets"]["target_a_response_propensity"]["eligible_records"] == 1
    assert report["prediction_targets"]["target_b_acceptance_propensity"]["eligible_records"] == 1
    assert report["prediction_targets"]["target_c_donation_completion"]["eligible_records"] == 0  # Prod is not completed


def test_e2e_unauthorized_requests_rejected(client, patient_token, donor_token):
    """
    Verifies that RBAC and consent access boundaries are strictly enforced.
    """
    # 1. Unauthenticated request rejected
    res_unauth = client.post(
        "/api/v1/blood/interactions/candidate",
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    assert res_unauth.status_code == 401

    # 2. Patient role cannot select candidates
    res_patient = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {patient_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    assert res_patient.status_code == 403

    # 3. Donor role cannot dispatch candidate selection
    res_donor = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    assert res_donor.status_code == 403


def test_e2e_transaction_atomicity_and_audit_consistency(client, doctor_token, db):
    """
    Verifies that interaction lifecycle changes and their corresponding audit logs
    are committed atomically in the same database transaction.
    """
    initial_audits = db.query(AuditLog).count()
    initial_ints = db.query(DonorEmergencyInteraction).count()

    # Step 1: Successful candidate selection commits both interaction and audit log atomically
    res_sel = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    assert res_sel.status_code == 201
    int_id = res_sel.json()["id"]

    assert db.query(DonorEmergencyInteraction).count() == initial_ints + 1
    assert db.query(AuditLog).count() == initial_audits + 1

    # Verify audit log specifically references this interaction
    recent_audit = db.query(AuditLog).filter(AuditLog.resource_id == int_id).first()
    assert recent_audit is not None
    assert "candidate" in recent_audit.action.lower() or "selected" in recent_audit.action.lower()
    assert recent_audit.status == "success"

    # Step 2: Ineligible donor selection is rejected with 400 and does NOT create an interaction record
    res_ineligible = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-103"},  # D-103 is medically ineligible
    )
    assert res_ineligible.status_code == 400
    # Invariant: No interaction record was created for D-103
    d103_int = db.query(DonorEmergencyInteraction).filter(DonorEmergencyInteraction.donor_id == "D-103").first()
    assert d103_int is None


def test_e2e_donation_completion_requires_prior_acceptance(client, doctor_token, db):
    """
    Verifies that donation completion cannot be recorded on a pending or unaccepted interaction,
    preserving clinical transfusion safety invariants.
    """
    res_sel = client.post(
        "/api/v1/blood/interactions/candidate",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102", "donorId": "D-101"},
    )
    int_id = res_sel.json()["id"]

    # Attempting to complete donation directly on pending candidate must fail
    res_comp = client.post(
        f"/api/v1/blood/interactions/{int_id}/complete",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"completionStatus": "completed", "unitsDonated": 1},
    )
    assert res_comp.status_code == 400
    assert "non-accepted" in res_comp.json()["message"].lower() or "acceptance" in res_comp.json()["message"].lower()


def test_e2e_canonical_database_configuration():
    """
    Verifies that Settings.DATABASE_URL resolves deterministically to the
    canonical database path and avoids relative-path ambiguity.
    """
    from app.core.config import settings
    import os

    db_url = settings.DATABASE_URL

    assert db_url.startswith("sqlite:///")

    clean_path = db_url.replace("sqlite:///", "", 1)

    assert os.path.isabs(clean_path)
    assert os.path.basename(clean_path) == "lifelink.db"
    assert os.path.isfile(clean_path)

    expected_path = os.path.normcase(
        os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "lifelink.db",
            )
        )
    )

    assert os.path.normcase(os.path.abspath(clean_path)) == expected_path
