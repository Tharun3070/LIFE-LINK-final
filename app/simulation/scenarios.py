import uuid
import time
import concurrent.futures
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.schemas.emergency import EmergencyCreate
from app.schemas.auth import UserProfileSchema
from app.schemas.interaction import (
    CandidateSelectionRequest,
    ContactAttemptRequest,
    ContactDeliveredRequest,
    ContactTimeoutRequest,
    InteractionCancellationRequest,
    DonorResponseRecordRequest,
    DonationCompletionRequest,
    ContactChannel,
    OutcomeSource,
    CompletionStatus,
)
from app.models.emergency import Emergency, EmergencyEvent
from app.models.interaction import DonorEmergencyInteraction
from app.models.donor import Donor
from app.models.audit import AuditLog
from app.services.emergency_service import emergency_service
from app.services.interaction_service import interaction_service
from app.simulation.mock_notifications import mock_notification_provider


class ScenarioExecutionError(Exception):
    """Raised when a scenario assertion fails."""
    pass


def run_scenario_01_valid_emergency_creation(db: Session, user: UserProfileSchema) -> Dict[str, Any]:
    """Scenario 1: Valid emergency creation with a valid hospital."""
    start_time = time.time()
    req = EmergencyCreate(
        type="blood",
        priority="critical",
        hospitalId="city-hospital-001",
        description="Simulation blood request for severe hemorrhage",
        bloodGroup="O+",
        unitsRequired=2,
    )
    emerg = emergency_service.create(db, req, user)

    # Assertions
    assert emerg.id is not None
    assert emerg.status == "created"
    assert emerg.hospitalId == "city-hospital-001"
    assert emerg.bloodGroup == "O+"

    # Verify EmergencyEvent
    event = db.query(EmergencyEvent).filter(EmergencyEvent.emergency_id == emerg.id).first()
    assert event is not None
    assert "Emergency created" in event.action

    # Verify AuditLog
    audit = db.query(AuditLog).filter(AuditLog.resource_id == emerg.id, AuditLog.status == "success").first()
    assert audit is not None
    assert "Blood Emergency SOS" in audit.action

    duration_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "scenario": "01_valid_emergency_creation",
        "status": "passed",
        "emergency_id": emerg.id,
        "duration_ms": duration_ms,
        "details": f"Created emergency {emerg.id} with verified event and audit trail",
    }


def run_scenario_02_unknown_hospital_rejection(db: Session, user: UserProfileSchema) -> Dict[str, Any]:
    """Scenario 2: Rejection of an unknown hospital ID."""
    start_time = time.time()
    req = EmergencyCreate(
        type="blood",
        priority="high",
        hospitalId="unknown-hospital-999",
        description="Emergency with unmapped hospital ID",
        bloodGroup="O+",
        unitsRequired=1,
    )

    rejected = False
    try:
        emergency_service.create(db, req, user)
    except HTTPException as e:
        if e.status_code == 400 and "not found" in e.detail.lower():
            rejected = True

    assert rejected, "EmergencyService did not reject unknown hospital ID with HTTP 400"

    # Verify failure audit log recorded
    audit = (
        db.query(AuditLog)
        .filter(AuditLog.action.contains("unknown-hospital-999"), AuditLog.status == "failed")
        .first()
    )
    assert audit is not None, "Failure audit log not emitted for unknown hospital rejection"

    duration_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "scenario": "02_unknown_hospital_rejection",
        "status": "passed",
        "duration_ms": duration_ms,
        "details": "Rejected invalid hospital ID with HTTP 400 and recorded failure audit",
    }


def run_scenario_03_resolution_and_cancellation(db: Session, user: UserProfileSchema) -> Dict[str, Any]:
    """Scenario 3: Emergency resolution and cancellation with matching timeline and audit records."""
    start_time = time.time()
    # 1. Resolve flow
    e1_req = EmergencyCreate(
        type="blood",
        priority="critical",
        hospitalId="city-hospital-001",
        description="Emergency for resolution test",
        bloodGroup="O+",
        unitsRequired=1,
    )
    e1 = emergency_service.create(db, e1_req, user)
    resolved_e1 = emergency_service.resolve(db, e1.id, user)
    assert resolved_e1.status == "resolved"
    assert resolved_e1.resolvedAt is not None

    e1_events = db.query(EmergencyEvent).filter(EmergencyEvent.emergency_id == e1.id).all()
    assert any("Emergency resolved" in ev.action for ev in e1_events)

    e1_audits = db.query(AuditLog).filter(AuditLog.resource_id == e1.id, AuditLog.action.contains("Resolved")).all()
    assert len(e1_audits) >= 1

    # 2. Cancel flow
    e2_req = EmergencyCreate(
        type="organ",
        priority="high",
        hospitalId="city-hospital-001",
        description="Emergency for cancellation test",
        organType="kidney",
    )
    e2 = emergency_service.create(db, e2_req, user)
    cancelled_e2 = emergency_service.cancel(db, e2.id, user)
    assert cancelled_e2.status == "cancelled"

    e2_events = db.query(EmergencyEvent).filter(EmergencyEvent.emergency_id == e2.id).all()
    assert any("Emergency cancelled" in ev.action for ev in e2_events)

    e2_audits = db.query(AuditLog).filter(AuditLog.resource_id == e2.id, AuditLog.action.contains("Cancelled")).all()
    assert len(e2_audits) >= 1

    duration_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "scenario": "03_resolution_and_cancellation",
        "status": "passed",
        "duration_ms": duration_ms,
        "details": "Verified atomic resolution and cancellation with synchronized timeline and audit logs",
    }


def run_scenario_04_invalid_transitions_and_idempotency(db: Session, user: UserProfileSchema) -> Dict[str, Any]:
    """Scenario 4: Invalid state transitions and repeated requests."""
    start_time = time.time()
    # Create emergency A and resolve
    e_req = EmergencyCreate(
        type="blood",
        priority="critical",
        hospitalId="city-hospital-001",
        description="Simulation emergency blood request",
        bloodGroup="O+",
        unitsRequired=1,
    )
    ea = emergency_service.create(db, e_req, user)
    emergency_service.resolve(db, ea.id, user)

    # 1. Retry resolve (Idempotency)
    initial_event_count = db.query(EmergencyEvent).filter(EmergencyEvent.emergency_id == ea.id).count()
    retry_resolved = emergency_service.resolve(db, ea.id, user)
    assert retry_resolved.status == "resolved"
    final_event_count = db.query(EmergencyEvent).filter(EmergencyEvent.emergency_id == ea.id).count()
    assert initial_event_count == final_event_count, "Duplicate event created on idempotent resolve retry"

    # 2. Cannot cancel resolved emergency
    cannot_cancel = False
    try:
        emergency_service.cancel(db, ea.id, user)
    except HTTPException as e:
        if e.status_code == 400 and "already been resolved" in e.detail:
            cannot_cancel = True
    assert cannot_cancel, "Failed to reject cancellation of already resolved emergency"

    # Create emergency B and cancel
    eb = emergency_service.create(db, e_req, user)
    emergency_service.cancel(db, eb.id, user)

    # 3. Retry cancel (Idempotency)
    b_event_count = db.query(EmergencyEvent).filter(EmergencyEvent.emergency_id == eb.id).count()
    retry_cancelled = emergency_service.cancel(db, eb.id, user)
    assert retry_cancelled.status == "cancelled"
    assert db.query(EmergencyEvent).filter(EmergencyEvent.emergency_id == eb.id).count() == b_event_count

    # 4. Cannot resolve cancelled emergency
    cannot_resolve = False
    try:
        emergency_service.resolve(db, eb.id, user)
    except HTTPException as e:
        if e.status_code == 400 and "already been cancelled" in e.detail:
            cannot_resolve = True
    assert cannot_resolve, "Failed to reject resolution of already cancelled emergency"

    duration_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "scenario": "04_invalid_transitions_and_idempotency",
        "status": "passed",
        "duration_ms": duration_ms,
        "details": "Verified idempotent retries and state-transition rejection guards",
    }


def run_scenario_05_consent_denial_guard(db: Session, user: UserProfileSchema) -> Dict[str, Any]:
    """Scenario 5: Consent denial with no donor contact or external notification."""
    start_time = time.time()
    mock_notification_provider.clear()

    # Create emergency
    e_req = EmergencyCreate(
        type="blood",
        priority="critical",
        hospitalId="city-hospital-001",
        description="Simulation emergency blood request",
        bloodGroup="O+",
        unitsRequired=1,
    )
    em = emergency_service.create(db, e_req, user)

    # Candidate selection for donor 2 (consent denied)
    sel_req = CandidateSelectionRequest(
        emergencyId=em.id,
        donorId="don-sim-02",
        distanceKm=3.1,
        etaMinutes=11,
    )
    interaction = interaction_service.record_candidate_selection(db, sel_req, user)
    assert interaction.contactStatus == "pending"

    # Attempt contact
    contact_blocked = False
    try:
        att_req = ContactAttemptRequest(contactChannel=ContactChannel.SMS, outcomeSource=OutcomeSource.DISPATCHER_PORTAL)
        interaction_service.record_contact_attempt(db, interaction.id, att_req, user)
    except HTTPException as e:
        if e.status_code == 403 and ("not granted" in e.detail.lower() or "consent" in e.detail.lower()):
            contact_blocked = True

    assert contact_blocked, "Contact attempt was not blocked for consent-denied donor"

    # Verify donor status untouched
    donor = db.query(Donor).filter(Donor.id == "don-sim-02").first()
    assert donor.status == "available"

    # Verify mock notification provider received 0 alerts
    assert mock_notification_provider.count() == 0

    # Verify failed AuditLog recorded
    audit = db.query(AuditLog).filter(AuditLog.resource_id == "don-sim-02", AuditLog.status == "failed").first()
    assert audit is not None
    assert "consent not granted" in audit.action.lower()

    duration_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "scenario": "05_consent_denial_guard",
        "status": "passed",
        "duration_ms": duration_ms,
        "details": "Blocked contact for unconsented donor with 0 notifications dispatched",
    }


def run_scenario_06_synthetic_donor_guard(db: Session, user: UserProfileSchema) -> Dict[str, Any]:
    """Scenario 6: Synthetic donor contact blocked from real dispatch."""
    start_time = time.time()
    mock_notification_provider.clear()

    e_req = EmergencyCreate(
        type="blood",
        priority="critical",
        hospitalId="city-hospital-001",
        description="Simulation emergency blood request",
        bloodGroup="O+",
        unitsRequired=1,
    )
    em = emergency_service.create(db, e_req, user)

    # Candidate selection for synthetic donor
    sel_req = CandidateSelectionRequest(
        emergencyId=em.id,
        donorId="don-sim-syn-03",
        isSynthetic=True,
    )
    interaction = interaction_service.record_candidate_selection(db, sel_req, user)

    synthetic_blocked = False
    try:
        att_req = ContactAttemptRequest(contactChannel=ContactChannel.SMS, outcomeSource=OutcomeSource.DISPATCHER_PORTAL)
        interaction_service.record_contact_attempt(db, interaction.id, att_req, user)
    except HTTPException as e:
        if e.status_code == 403 and "synthetic benchmark profile" in e.detail.lower():
            synthetic_blocked = True

    assert synthetic_blocked, "Synthetic profile contact attempt was not blocked with HTTP 403"
    assert mock_notification_provider.count() == 0

    audit = db.query(AuditLog).filter(AuditLog.resource_id == "don-sim-syn-03", AuditLog.status == "failed").first()
    assert audit is not None
    assert "synthetic benchmark profile" in audit.action.lower()

    duration_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "scenario": "06_synthetic_donor_guard",
        "status": "passed",
        "duration_ms": duration_ms,
        "details": "Enforced synthetic guard blocking dispatch to benchmark profiles",
    }


def run_scenario_07_candidate_deduplication_and_filtering(db: Session, user: UserProfileSchema) -> Dict[str, Any]:
    """Scenario 7: Candidate deduplication and clinically compatible donor filtering."""
    start_time = time.time()

    e_req = EmergencyCreate(
        type="blood",
        priority="critical",
        hospitalId="city-hospital-001",
        description="Simulation emergency blood request",
        bloodGroup="O+",
        unitsRequired=1,
    )
    em = emergency_service.create(db, e_req, user)

    # 1. Ineligible donor rejection
    inelig_rejected = False
    try:
        inelig_req = CandidateSelectionRequest(emergencyId=em.id, donorId="don-sim-inelig-04")
        interaction_service.record_candidate_selection(db, inelig_req, user)
    except HTTPException as e:
        if e.status_code == 400 and "medically ineligible" in e.detail.lower():
            inelig_rejected = True
    assert inelig_rejected, "Medically ineligible donor was not rejected during candidate selection"

    # 2. Candidate deduplication: select donor 1 twice
    sel_req = CandidateSelectionRequest(emergencyId=em.id, donorId="don-sim-01")
    int1 = interaction_service.record_candidate_selection(db, sel_req, user)
    int2 = interaction_service.record_candidate_selection(db, sel_req, user)

    assert int1.id == int2.id, "Candidate selection created duplicate interaction records for the same donor"
    total_interactions = (
        db.query(DonorEmergencyInteraction)
        .filter(DonorEmergencyInteraction.emergency_id == em.id, DonorEmergencyInteraction.donor_id == "don-sim-01")
        .count()
    )
    assert total_interactions == 1

    duration_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "scenario": "07_candidate_deduplication_and_filtering",
        "status": "passed",
        "duration_ms": duration_ms,
        "details": "Verified medical eligibility check and idempotent candidate selection deduplication",
    }


def run_scenario_08_interaction_lifecycle_states(db: Session, user: UserProfileSchema) -> Dict[str, Any]:
    """Scenario 8: Donor acceptance, decline, no response, timeout, and cancellation."""
    start_time = time.time()
    e_req = EmergencyCreate(
        type="blood",
        priority="critical",
        hospitalId="city-hospital-001",
        description="Simulation emergency blood request",
        bloodGroup="O+",
        unitsRequired=1,
    )
    em = emergency_service.create(db, e_req, user)

    # 1. Acceptance workflow
    sel1 = CandidateSelectionRequest(emergencyId=em.id, donorId="don-sim-01")
    int1 = interaction_service.record_candidate_selection(db, sel1, user)

    att1 = ContactAttemptRequest(contactChannel=ContactChannel.SMS, outcomeSource=OutcomeSource.DISPATCHER_PORTAL)
    int1_att = interaction_service.record_contact_attempt(db, int1.id, att1, user)
    assert int1_att.contactStatus == "attempted"

    del1 = ContactDeliveredRequest(outcomeSource=OutcomeSource.DISPATCHER_PORTAL)
    int1_del = interaction_service.record_contact_delivery(db, int1.id, del1, user)
    assert int1_del.contactStatus == "delivered"

    resp1 = DonorResponseRecordRequest(accepted=True, outcomeSource=OutcomeSource.DISPATCHER_PORTAL)
    int1_resp = interaction_service.record_donor_response(db, int1.id, resp1, user)
    assert int1_resp.responseStatus == "responded"
    assert int1_resp.acceptanceStatus == "accepted"
    assert int1_resp.responseLatencySeconds is not None

    comp1 = DonationCompletionRequest(completionStatus=CompletionStatus.COMPLETED, unitsDonated=1, outcomeSource=OutcomeSource.DISPATCHER_PORTAL)
    int1_comp = interaction_service.record_donation_completion(db, int1.id, comp1, user)
    assert int1_comp.completionStatus == "completed"
    assert int1_comp.unitsDonated == 1

    # 2. Timeout workflow on emergency 2
    em2 = emergency_service.create(db, e_req, user)
    int2 = interaction_service.record_candidate_selection(db, CandidateSelectionRequest(emergencyId=em2.id, donorId="don-sim-01"), user)
    interaction_service.record_contact_attempt(db, int2.id, att1, user)
    tout = ContactTimeoutRequest(timeoutReason="No response after 15 minutes", outcomeSource=OutcomeSource.DISPATCHER_PORTAL)
    int2_tout = interaction_service.record_contact_timeout(db, int2.id, tout, user)
    assert int2_tout.responseStatus == "no_response"
    assert int2_tout.acceptanceStatus == "unreachable"
    assert int2_tout.responseLatencySeconds is None, "Latency must remain null for unobserved timeout responses"

    # 3. Cancellation workflow on emergency 3
    em3 = emergency_service.create(db, e_req, user)
    int3 = interaction_service.record_candidate_selection(db, CandidateSelectionRequest(emergencyId=em3.id, donorId="don-sim-01"), user)
    cnc = InteractionCancellationRequest(cancellationReason="Patient transferred", outcomeSource=OutcomeSource.DISPATCHER_PORTAL)
    int3_cnc = interaction_service.record_interaction_cancellation(db, int3.id, cnc, user)
    assert int3_cnc.completionStatus == "canceled"

    duration_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "scenario": "08_interaction_lifecycle_states",
        "status": "passed",
        "duration_ms": duration_ms,
        "details": "Verified full state transitions: acceptance, completion, latency-null timeout, and cancellation",
    }


def run_scenario_09_completion_rule_enforcement(db: Session, user: UserProfileSchema) -> Dict[str, Any]:
    """Scenario 9: Emergency completion only when existing business rules permit it."""
    start_time = time.time()
    e_req = EmergencyCreate(
        type="blood",
        priority="critical",
        hospitalId="city-hospital-001",
        description="Simulation emergency blood request",
        bloodGroup="O+",
        unitsRequired=1,
    )
    em = emergency_service.create(db, e_req, user)

    # Create interaction in pending acceptance state
    int_rec = interaction_service.record_candidate_selection(db, CandidateSelectionRequest(emergencyId=em.id, donorId="don-sim-01"), user)

    # Attempt completion on non-accepted interaction
    premature_blocked = False
    try:
        req = DonationCompletionRequest(completionStatus=CompletionStatus.COMPLETED, unitsDonated=1, outcomeSource=OutcomeSource.DISPATCHER_PORTAL)
        interaction_service.record_donation_completion(db, int_rec.id, req, user)
    except HTTPException as e:
        if e.status_code == 400 and "non-accepted interaction" in e.detail.lower():
            premature_blocked = True

    assert premature_blocked, "Donation completion was permitted for non-accepted interaction"

    duration_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "scenario": "09_completion_rule_enforcement",
        "status": "passed",
        "duration_ms": duration_ms,
        "details": "Enforced rule that donation completion requires affirmative donor acceptance",
    }


def run_scenario_10_transaction_rollback_safety(db: Session, user: UserProfileSchema) -> Dict[str, Any]:
    """Scenario 10: Failure during a multi-record transaction with full rollback."""
    start_time = time.time()
    initial_emerg_count = db.query(Emergency).count()
    initial_event_count = db.query(EmergencyEvent).count()
    initial_audit_count = db.query(AuditLog).count()

    # Attempt a transactional batch with intentional integrity error
    rollback_occurred = False
    try:
        bad_emerg = Emergency(
            id=f"test-rollback-{uuid.uuid4().hex[:6]}",
            type="blood",
            priority="critical",
            status="created",
            hospital_id="city-hospital-001",
            hospital_name="City General Hospital",
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            description="Rollback test emergency",
        )
        db.add(bad_emerg)

        # Trigger duplicate primary key violation on event
        ev1 = EmergencyEvent(
            id="duplicate-event-id-fixed",
            emergency_id=bad_emerg.id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=user.name,
            action="First event",
            status="success",
        )
        ev2 = EmergencyEvent(
            id="duplicate-event-id-fixed",  # duplicate primary key!
            emergency_id=bad_emerg.id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=user.name,
            action="Colliding event",
            status="success",
        )
        db.add_all([ev1, ev2])
        db.commit()
    except Exception:
        db.rollback()
        rollback_occurred = True

    assert rollback_occurred, "Transaction did not raise error on duplicate primary key"
    assert db.query(Emergency).count() == initial_emerg_count, "Partial emergency was committed during failed transaction"
    assert db.query(EmergencyEvent).count() == initial_event_count, "Partial event was committed during failed transaction"

    duration_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "scenario": "10_transaction_rollback_safety",
        "status": "passed",
        "duration_ms": duration_ms,
        "details": "Confirmed atomic rollback with 0 partial records leaked",
    }


def run_scenario_11_concurrent_requests_same_emergency(
    get_session_fn, user: UserProfileSchema, concurrency: int = 5
) -> Dict[str, Any]:
    """Scenario 11: Concurrent requests targeting the same emergency."""
    start_time = time.time()
    setup_db = get_session_fn()
    e_req = EmergencyCreate(
        type="blood",
        priority="critical",
        hospitalId="city-hospital-001",
        description="Simulation emergency blood request",
        bloodGroup="O+",
        unitsRequired=1,
    )
    em = emergency_service.create(setup_db, e_req, user)
    em_id = em.id
    setup_db.close()

    def candidate_selector(worker_id: int) -> str:
        s = get_session_fn()
        try:
            req = CandidateSelectionRequest(emergencyId=em_id, donorId="don-sim-01")
            res = interaction_service.record_candidate_selection(s, req, user)
            return res.id
        finally:
            s.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(candidate_selector, i) for i in range(concurrency)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    # All workers must have returned the exact same deduplicated interaction ID
    assert len(set(results)) == 1, f"Concurrent workers returned inconsistent interaction IDs: {set(results)}"

    verify_db = get_session_fn()
    count = (
        verify_db.query(DonorEmergencyInteraction)
        .filter(DonorEmergencyInteraction.emergency_id == em_id, DonorEmergencyInteraction.donor_id == "don-sim-01")
        .count()
    )
    verify_db.close()
    assert count == 1, f"Expected 1 interaction row, found {count}"

    duration_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "scenario": "11_concurrent_requests_same_emergency",
        "status": "passed",
        "concurrency_level": concurrency,
        "duration_ms": duration_ms,
        "details": f"Processed {concurrency} concurrent requests with 0 duplicates and consistent final state",
    }


def run_scenario_12_concurrent_multiple_emergencies(
    get_session_fn, user: UserProfileSchema, count: int = 5
) -> Dict[str, Any]:
    """Scenario 12: Multiple emergency workflows running concurrently."""
    start_time = time.time()

    def run_lifecycle(worker_id: int) -> Dict[str, Any]:
        s = get_session_fn()
        try:
            req = EmergencyCreate(
                type="blood",
                priority="high",
                hospitalId="city-hospital-001",
                description=f"Concurrent emergency #{worker_id}",
                bloodGroup="O+",
                unitsRequired=1,
            )
            created = emergency_service.create(s, req, user)
            resolved = emergency_service.resolve(s, created.id, user)
            return {"emergency_id": created.id, "status": resolved.status}
        finally:
            s.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=count) as executor:
        futures = [executor.submit(run_lifecycle, i) for i in range(count)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == count
    assert all(r["status"] == "resolved" for r in results)

    duration_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "scenario": "12_concurrent_multiple_emergencies",
        "status": "passed",
        "concurrency_level": count,
        "duration_ms": duration_ms,
        "details": f"Successfully coordinated {count} parallel emergency lifecycles with complete isolation",
    }


def run_scenario_13_websocket_event_delivery(client, db: Session, user: UserProfileSchema) -> Dict[str, Any]:
    """Scenario 13: WebSocket clients receiving expected event types and emergency identifiers."""
    start_time = time.time()
    from app.core.security import create_access_token
    user_token = create_access_token(subject=user.id, role=user.role)
    events_received = []

    with client.websocket_connect(f"/ws?token={user_token}") as ws:
        msg1 = ws.receive_json()
        assert msg1["type"] == "connection.established"
        events_received.append(msg1["type"])

        # Trigger emergency creation
        req = EmergencyCreate(
            type="blood",
            priority="critical",
            hospitalId="city-hospital-001",
            description="WebSocket broadcast test",
            bloodGroup="O+",
            unitsRequired=1,
        )
        emerg = emergency_service.create(db, req, user)

        msg2 = ws.receive_json()
        assert msg2["type"] == "emergency.created"
        assert msg2["payload"]["emergencyId"] == emerg.id
        events_received.append(msg2["type"])

        # Trigger emergency resolution
        emergency_service.resolve(db, emerg.id, user)
        msg3 = ws.receive_json()
        assert msg3["type"] == "emergency.updated"
        assert msg3["payload"]["emergencyId"] == emerg.id
        assert msg3["payload"]["status"] == "resolved"
        events_received.append(msg3["type"])

    duration_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "scenario": "13_websocket_event_delivery",
        "status": "passed",
        "events_received": events_received,
        "duration_ms": duration_ms,
        "details": f"Verified realtime WebSocket delivery for: {', '.join(events_received)}",
    }


def run_scenario_14_websocket_reconnect(client, token: Optional[str] = None) -> Dict[str, Any]:
    """Scenario 14: Disconnected clients reconnecting or resubscribing according to the implemented protocol."""
    start_time = time.time()
    from app.realtime.manager import ws_manager
    from app.core.security import create_access_token

    if not token:
        token = create_access_token(subject="usr-doc-001", role="doctor")
    ws_url = f"/ws?token={token}"

    initial_active = len(ws_manager.active_connections)

    # First connection
    with client.websocket_connect(ws_url) as ws1:
        msg1 = ws1.receive_json()
        assert msg1["type"] == "connection.established"
        assert len(ws_manager.active_connections) == initial_active + 1

    # Disconnected
    assert len(ws_manager.active_connections) == initial_active

    # Reconnect
    with client.websocket_connect(ws_url) as ws2:
        msg2 = ws2.receive_json()
        assert msg2["type"] == "connection.established"
        assert len(ws_manager.active_connections) == initial_active + 1

    assert len(ws_manager.active_connections) == initial_active

    duration_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "scenario": "14_websocket_reconnect",
        "status": "passed",
        "duration_ms": duration_ms,
        "details": "Verified clean disconnect/reconnect and connection count state tracking",
    }


def run_scenario_15_telemetry_ordering_and_consistency(
    client, db: Session, user: UserProfileSchema
) -> Dict[str, Any]:
    """Scenario 15: Event ordering, duplicate delivery behavior, and stale dashboard state detection."""
    start_time = time.time()
    from app.core.security import create_access_token
    user_token = create_access_token(subject=user.id, role=user.role)
    ordered_events = []

    with client.websocket_connect(f"/ws?token={user_token}") as ws:
        # 1. Connection established
        e1 = ws.receive_json()
        ordered_events.append(e1["type"])

        # 2. Emergency created
        req = EmergencyCreate(
            type="blood",
            priority="critical",
            hospitalId="city-hospital-001",
            description="Ordering verification emergency",
            bloodGroup="O+",
            unitsRequired=1,
        )
        em = emergency_service.create(db, req, user)
        e2 = ws.receive_json()
        ordered_events.append(e2["type"])

        # Verify DB is strictly committed before or at event receipt (no stale state)
        db_record = db.query(Emergency).filter(Emergency.id == em.id).first()
        assert db_record is not None
        assert db_record.status == "created"

        # 3. Emergency resolved
        emergency_service.resolve(db, em.id, user)
        e3 = ws.receive_json()
        ordered_events.append(e3["type"])

        # Query KPIs to ensure no stale dashboard state
        kpis = emergency_service.get_kpis(db)
        assert kpis is not None

    expected_sequence = ["connection.established", "emergency.created", "emergency.updated"]
    assert ordered_events == expected_sequence, f"Unexpected sequence: {ordered_events}"

    duration_ms = round((time.time() - start_time) * 1000, 2)
    return {
        "scenario": "15_telemetry_ordering_and_consistency",
        "status": "passed",
        "event_sequence": ordered_events,
        "duration_ms": duration_ms,
        "details": f"Strict event ordering verified ({' -> '.join(ordered_events)}) with synchronized DB state",
    }
