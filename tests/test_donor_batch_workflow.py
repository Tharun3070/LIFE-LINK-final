"""
LifeLink Batch Donor Matching & Outreach Workflow Test Suite.
File: tests/test_donor_batch_workflow.py

Validates:
1. Selection of five nearest eligible donors per batch when at least five are available.
2. Selection of all available when fewer than five are in the eligible pool.
3. Sending mock notifications and recording donor response.
4. Google Maps routes calculated ONLY for donors who explicitly accept.
5. Aiming for three accepted donors: workflow stops when 3 accept.
6. Progressive search radius expansion when fewer than three accept.
7. Duplicate contact prevention for the same emergency across multiple batches.
8. Role-based security on dispatch-batch endpoint.
9. Workflow status reporting accuracy.
"""

from datetime import datetime, timezone
from unittest.mock import patch
import pytest

from app.models.donor import Donor
from app.models.emergency import Emergency
from app.models.hospital import Hospital
from app.models.interaction import DonorEmergencyInteraction
from app.models.user import User
from app.models.consent import Consent
from app.services.donor_service import donor_service
from app.simulation.mock_notifications import mock_notification_provider
from app.geo.service import geospatial_service
from app.core.config import settings


@pytest.fixture(autouse=True)
def enforce_mock_notifications(monkeypatch):
    """Enforces mock-only notifications and carrier isolation during tests."""
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "")
    monkeypatch.setattr(settings, "GOOGLE_MAPS_API_KEY", "")
    monkeypatch.setattr(settings, "MOCK_NOTIFICATIONS_ONLY", True)
    monkeypatch.setattr(settings, "NOTIFICATION_PROVIDER", "mock")
    geospatial_service.api_key = ""
    mock_notification_provider.clear()


@pytest.fixture
def workflow_setup(db):
    """
    Sets up an emergency scenario:
    Hospital: KMCH (11.0558, 77.0345)
    Emergency: Gandhipuram (11.0183, 76.9639)
    Blood Group: O-
    """
    mock_notification_provider.clear()
    geospatial_service.clear_cache()

    hospital = Hospital(
        id="hosp-kmch-wf",
        name="Kovai Medical Center and Hospital",
        address="Avinashi Road",
        city="Coimbatore",
        lat=11.0558,
        lng=77.0345,
        type="Tertiary Trauma",
        blood_bank_available=True,
    )
    db.add(hospital)

    now_str = datetime.now(timezone.utc).isoformat()
    emergency = Emergency(
        id="EMG-WF-001",
        type="blood",
        priority="critical",
        status="active",
        hospital_id="hosp-kmch-wf",
        hospital_name="Kovai Medical Center and Hospital",
        created_at=now_str,
        updated_at=now_str,
        description="Trauma donor matching test workflow",
        blood_group="O-",
        units_required=2,
        location_lat=11.0183,
        location_lng=76.9639,
    )
    db.add(emergency)
    db.commit()
    return hospital, emergency


def test_select_five_nearest_eligible_donors_when_five_or_more_available(db, workflow_setup):
    """
    When 7 compatible eligible donors are available within radius,
    selects exactly 5 nearest eligible donors for the batch.
    """
    hosp, emerg = workflow_setup
    # Create 7 donors at varying distances from emergency (11.0183, 76.9639)
    # D1 ~0.2 km, D2 ~0.4 km, D3 ~0.6 km, D4 ~0.8 km, D5 ~1.0 km, D6 ~1.2 km, D7 ~1.4 km
    donors = [
        Donor(id=f"D-5BATCH-{i}", blood_group="O-", eligibility="eligible", status="available", lat=11.0183 + (i * 0.002), lng=76.9639)
        for i in range(1, 8)
    ]
    db.add_all(donors)
    db.commit()

    batch_info = donor_service.select_emergency_donor_batch(db, emergency_id="EMG-WF-001", batch_size=5)
    selected = batch_info["selectedCandidates"]

    assert len(selected) == 5
    selected_ids = [c["donor"].id for c in selected]
    # Nearest 5 donors must be selected in ascending distance order
    assert selected_ids == ["D-5BATCH-1", "D-5BATCH-2", "D-5BATCH-3", "D-5BATCH-4", "D-5BATCH-5"]


def test_select_fewer_than_five_when_limited_pool(db, workflow_setup):
    """
    When only 3 compatible eligible donors exist, selects all 3.
    """
    hosp, emerg = workflow_setup
    donors = [
        Donor(id=f"D-LIM-{i}", blood_group="O-", eligibility="eligible", status="available", lat=11.0183 + (i * 0.003), lng=76.9639)
        for i in range(1, 4)
    ]
    db.add_all(donors)
    db.commit()

    batch_info = donor_service.select_emergency_donor_batch(db, emergency_id="EMG-WF-001", batch_size=5)
    selected = batch_info["selectedCandidates"]
    assert len(selected) == 3


def test_mock_notifications_and_recording_donor_responses(db, workflow_setup):
    """
    Dispatches mock notifications with carrier isolation, maps to test contact pool,
    and accurately records donor acceptance and decline responses.
    """
    hosp, emerg = workflow_setup
    donors = [
        Donor(id=f"D-NOTIF-{i}", blood_group="O-", eligibility="eligible", status="available", lat=11.0183 + (i * 0.002), lng=76.9639)
        for i in range(1, 6)
    ]
    db.add_all(donors)
    db.commit()

    res = donor_service.dispatch_emergency_donor_batch(db, emergency_id="EMG-WF-001", batch_size=5)
    assert res.donorsContactedCount == 5
    assert len(res.contactedDonors) == 5
    assert mock_notification_provider.count() == 5

    # Check that interactions are created with pending status
    interactions = db.query(DonorEmergencyInteraction).filter(DonorEmergencyInteraction.emergency_id == "EMG-WF-001").all()
    assert len(interactions) == 5
    for inter in interactions:
        assert inter.contact_status == "attempted"
        assert inter.acceptance_status == "pending"

    # Donor 1 accepts
    resp1 = donor_service.record_donor_response(db, donor_id="D-NOTIF-1", status_choice="accepted")
    assert resp1["status"] == "accepted"

    # Donor 2 declines
    resp2 = donor_service.record_donor_response(db, donor_id="D-NOTIF-2", status_choice="declined")
    assert resp2["status"] == "declined"

    int1 = db.query(DonorEmergencyInteraction).filter(DonorEmergencyInteraction.donor_id == "D-NOTIF-1").first()
    assert int1.acceptance_status == "accepted"
    int2 = db.query(DonorEmergencyInteraction).filter(DonorEmergencyInteraction.donor_id == "D-NOTIF-2").first()
    assert int2.acceptance_status == "declined"


def test_routes_calculated_only_for_donors_who_explicitly_accept(db, workflow_setup):
    """
    CRITICAL REQUIREMENT:
    Google Maps road routes and ETA are calculated ONLY for donors who explicitly accept,
    NOT during candidate batch selection or dispatch.
    """
    hosp, emerg = workflow_setup
    d1 = Donor(id="D-ROUTE-ACC", blood_group="O-", eligibility="eligible", status="available", lat=11.0200, lng=76.9650)
    d2 = Donor(id="D-ROUTE-DEC", blood_group="O-", eligibility="eligible", status="available", lat=11.0210, lng=76.9660)
    db.add_all([d1, d2])
    db.commit()

    # Step 1: Batch dispatch. Distance matrix should NOT be called.
    with patch.object(geospatial_service, "calculate_distance_and_eta_sync") as mock_calc:
        res = donor_service.dispatch_emergency_donor_batch(db, emergency_id="EMG-WF-001", batch_size=5)
        assert res.donorsContactedCount == 2
        # No Google Maps route calculation during dispatch!
        assert mock_calc.call_count == 0

    # Step 2: Donor 2 declines. Route calculation should NOT be called.
    with patch.object(geospatial_service, "calculate_distance_and_eta_sync") as mock_calc:
        donor_service.record_donor_response(db, donor_id="D-ROUTE-DEC", status_choice="declined")
        assert mock_calc.call_count == 0

    # Step 3: Donor 1 explicitly accepts. Route calculation MUST be called for the accepted donor!
    mock_geo_result = {
        "road_distance_km": 4.5,
        "eta_minutes": 14,
        "mode": "google_maps_live",
        "distance_source": "google_maps_distance_matrix",
        "eta_source": "google_maps_live_traffic",
        "is_live_traffic": True,
    }
    with patch.object(geospatial_service, "calculate_distance_and_eta_sync", return_value=mock_geo_result) as mock_calc:
        donor_service.record_donor_response(db, donor_id="D-ROUTE-ACC", status_choice="accepted")
        assert mock_calc.call_count == 1

    int_acc = db.query(DonorEmergencyInteraction).filter(DonorEmergencyInteraction.donor_id == "D-ROUTE-ACC").first()
    assert int_acc.distance_km == 4.5
    assert int_acc.eta_minutes == 14


def test_aim_for_three_accepted_donors_and_stop(db, workflow_setup):
    """
    Workflow aims for 3 accepted donors.
    When 3 donors have explicitly accepted, dispatching new batches stops.
    """
    hosp, emerg = workflow_setup
    donors = [
        Donor(id=f"D-THREE-{i}", blood_group="O-", eligibility="eligible", status="available", lat=11.0183 + (i * 0.002), lng=76.9639)
        for i in range(1, 6)
    ]
    db.add_all(donors)
    db.commit()

    # Dispatch batch 1 (5 donors contacted)
    donor_service.dispatch_emergency_donor_batch(db, emergency_id="EMG-WF-001", batch_size=5)

    # 3 donors accept
    donor_service.record_donor_response(db, donor_id="D-THREE-1", status_choice="accepted")
    donor_service.record_donor_response(db, donor_id="D-THREE-2", status_choice="accepted")
    donor_service.record_donor_response(db, donor_id="D-THREE-3", status_choice="accepted")

    # Add 2 more available donors
    db.add(Donor(id="D-EXTRA-1", blood_group="O-", eligibility="eligible", status="available", lat=11.0185, lng=76.9640))
    db.commit()

    # Attempt to dispatch next batch
    res_next = donor_service.dispatch_emergency_donor_batch(db, emergency_id="EMG-WF-001", batch_size=5)
    assert res_next.targetReached is True
    assert res_next.acceptedDonorsCount == 3
    assert res_next.donorsContactedCount == 0
    assert "already reached" in res_next.message


def test_progressive_radius_expansion_when_fewer_than_three_accept(db, workflow_setup):
    """
    If fewer than 3 accept, the workflow progressively expands the search radius
    and contacts new eligible donors.
    """
    hosp, emerg = workflow_setup
    # 2 donors in initial 2 km radius (~0.5 km)
    d1 = Donor(id="D-RAD-01", blood_group="O-", eligibility="eligible", status="available", lat=11.0200, lng=76.9650)
    d2 = Donor(id="D-RAD-02", blood_group="O-", eligibility="eligible", status="available", lat=11.0210, lng=76.9660)
    # 3 donors in 5 km tier (~3.5 km)
    d3 = Donor(id="D-RAD-03", blood_group="O-", eligibility="eligible", status="available", lat=11.0450, lng=76.9750)
    d4 = Donor(id="D-RAD-04", blood_group="O-", eligibility="eligible", status="available", lat=11.0460, lng=76.9760)
    d5 = Donor(id="D-RAD-05", blood_group="O-", eligibility="eligible", status="available", lat=11.0470, lng=76.9770)
    db.add_all([d1, d2, d3, d4, d5])
    db.commit()

    # Batch 1 needs 5 donors: 2 km only has 2 donors, so it expands to 5 km to get 5 donors
    res_batch1 = donor_service.dispatch_emergency_donor_batch(db, emergency_id="EMG-WF-001", batch_size=5)
    assert res_batch1.donorsContactedCount == 5
    assert res_batch1.currentRadiusKm == 5.0

    # Only 1 donor accepts (D-RAD-01)
    donor_service.record_donor_response(db, donor_id="D-RAD-01", status_choice="accepted")
    # Others decline or do not respond
    donor_service.record_donor_response(db, donor_id="D-RAD-02", status_choice="declined")

    # Add 5 new donors in 10 km tier (~8 km)
    donors_10k = [
        Donor(id=f"D-RAD-10K-{i}", blood_group="O-", eligibility="eligible", status="available", lat=11.0850 + (i * 0.002), lng=76.9950)
        for i in range(1, 6)
    ]
    db.add_all(donors_10k)
    db.commit()

    # Batch 2: since only 1 has accepted (< 3 target), contacts the new donors in 10km tier
    res_batch2 = donor_service.dispatch_emergency_donor_batch(db, emergency_id="EMG-WF-001", batch_size=5)
    assert res_batch2.donorsContactedCount == 5
    assert res_batch2.currentRadiusKm == 10.0
    contacted_ids_b2 = [d.donorId for d in res_batch2.contactedDonors]
    assert len(contacted_ids_b2) == 5
    assert contacted_ids_b2[0] == "D-RAD-10K-1"


def test_prevent_duplicate_contacts_for_same_emergency(db, workflow_setup):
    """
    CRITICAL REQUIREMENT:
    Donors already contacted for an emergency must NEVER be contacted again
    in subsequent batches for that emergency.
    """
    hosp, emerg = workflow_setup
    d1 = Donor(id="D-DUP-01", blood_group="O-", eligibility="eligible", status="available", lat=11.0190, lng=76.9645)
    d2 = Donor(id="D-DUP-02", blood_group="O-", eligibility="eligible", status="available", lat=11.0195, lng=76.9650)
    d3 = Donor(id="D-DUP-03", blood_group="O-", eligibility="eligible", status="available", lat=11.0200, lng=76.9655)
    db.add_all([d1, d2, d3])
    db.commit()

    # Batch 1 contacts D-DUP-01 and D-DUP-02 (requesting batch_size=2)
    b1 = donor_service.dispatch_emergency_donor_batch(db, emergency_id="EMG-WF-001", batch_size=2)
    assert b1.donorsContactedCount == 2
    b1_ids = [d.donorId for d in b1.contactedDonors]
    assert b1_ids == ["D-DUP-01", "D-DUP-02"]

    # D-DUP-01 declines (target 3 not reached)
    donor_service.record_donor_response(db, donor_id="D-DUP-01", status_choice="declined")

    # Batch 2: Must NOT re-contact D-DUP-01 or D-DUP-02! Only D-DUP-03 should be contacted.
    b2 = donor_service.dispatch_emergency_donor_batch(db, emergency_id="EMG-WF-001", batch_size=2)
    assert b2.donorsContactedCount == 1
    assert b2.contactedDonors[0].donorId == "D-DUP-03"

    # Batch 3: All 3 donors have now been contacted. No more uncontacted donors remain.
    b3 = donor_service.dispatch_emergency_donor_batch(db, emergency_id="EMG-WF-001", batch_size=2)
    assert b3.donorsContactedCount == 0
    assert "No additional uncontacted eligible donors" in b3.message


def test_workflow_api_endpoints_and_rbac(client, doctor_token, patient_token, workflow_setup, db):
    """
    Tests POST /api/v1/blood/emergencies/{id}/dispatch-batch
    and GET /api/v1/blood/emergencies/{id}/workflow-status
    with role authorization checks.
    """
    hosp, emerg = workflow_setup
    d1 = Donor(id="D-API-01", blood_group="O-", eligibility="eligible", status="available", lat=11.0200, lng=76.9650)
    db.add(d1)
    db.commit()

    # Patient role is forbidden from triggering batch dispatch (HTTP 403)
    res_forbidden = client.post(
        "/api/v1/blood/emergencies/EMG-WF-001/dispatch-batch",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert res_forbidden.status_code == 403

    # Doctor role can trigger batch dispatch (HTTP 200)
    res_dispatch = client.post(
        "/api/v1/blood/emergencies/EMG-WF-001/dispatch-batch?batch_size=5",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert res_dispatch.status_code == 200
    data = res_dispatch.json()
    assert data["emergencyId"] == "EMG-WF-001"
    assert data["donorsContactedCount"] == 1
    assert data["targetAcceptedDonors"] == 3
    assert data["targetReached"] is False

    # Workflow status endpoint
    res_status = client.get("/api/v1/blood/emergencies/EMG-WF-001/workflow-status")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["emergencyId"] == "EMG-WF-001"
    assert status_data["totalContacted"] == 1
    assert status_data["totalPending"] == 1
    assert status_data["totalAccepted"] == 0
    assert status_data["targetReached"] is False
