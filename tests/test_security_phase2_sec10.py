"""
Tests for SEC-10: Audit Log Integrity and Cryptographic Tamper Evidence
Verifies:
1. Ordinary users (patients, donors) cannot access audit endpoints (403 Forbidden).
2. No audit mutation endpoints (POST/PUT/DELETE) are exposed to application clients.
3. Newly written audit logs automatically compute and populate previous_hash and record_hash.
4. Consecutive audit records form an unbroken cryptographic hash chain.
5. verify_chain detects content modification (tampering with actor, action, or timestamp).
6. verify_chain detects record omission (deleting an intermediate record).
7. Pre-chaining legacy logs with None hashes are gracefully preserved without failing verification.
8. Concurrent/multiple inserts in a session maintain integrity.
"""
import pytest
from datetime import datetime, timezone
from app.models.audit import AuditLog, compute_audit_hash, GENESIS_HASH
from app.services.audit_service import AuditService
from app.schemas.audit import AuditLogCreate


def test_sec10_unauthorized_users_denied_audit_access(client, patient_token, donor_token):
    """Patients and donors cannot access the audit log endpoints (403 Forbidden)."""
    # Patient
    resp_pat = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {patient_token}"})
    assert resp_pat.status_code == 403

    # Donor
    resp_dnr = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {donor_token}"})
    assert resp_dnr.status_code == 403


def test_sec10_no_public_audit_mutation_endpoints(client, doctor_token):
    """Audit logs cannot be modified or deleted via REST endpoints (Method Not Allowed / Not Found)."""
    # Attempt POST to /audit
    resp_post = client.post("/api/v1/audit", headers={"Authorization": f"Bearer {doctor_token}"}, json={})
    assert resp_post.status_code in (404, 405)

    # Attempt PUT/PATCH/DELETE to /audit/{id}
    resp_put = client.put("/api/v1/audit/audit-1", headers={"Authorization": f"Bearer {doctor_token}"}, json={})
    assert resp_put.status_code in (404, 405)

    resp_del = client.delete("/api/v1/audit/audit-1", headers={"Authorization": f"Bearer {doctor_token}"})
    assert resp_del.status_code in (404, 405)


def test_sec10_automatic_hash_chaining_on_creation(db):
    """AuditLog instances automatically compute previous_hash and record_hash."""
    import time

    t1 = datetime.now(timezone.utc).isoformat()
    log1 = AuditLog(
        id="audit-test-sec10-01",
        timestamp=t1,
        actor="Dr. Security Tester",
        actor_type="user",
        action="Reviewed Critical Patient File",
        resource="Emergency #BL-102",
        resource_id="BL-102",
        status="success",
        module="blood",
    )
    db.add(log1)
    db.commit()
    db.refresh(log1)

    assert log1.record_hash is not None
    assert len(log1.record_hash) == 64
    assert log1.previous_hash is not None

    # Insert second log in chain
    time.sleep(0.02)
    t2 = datetime.now(timezone.utc).isoformat()
    log2 = AuditLog(
        id="audit-test-sec10-02",
        timestamp=t2,
        actor="Dr. Security Tester",
        actor_type="user",
        action="Dispatched Blood Unit",
        resource="Emergency #BL-102",
        resource_id="BL-102",
        status="success",
        module="blood",
    )
    db.add(log2)
    db.commit()
    db.refresh(log2)

    assert log2.record_hash is not None
    assert log2.previous_hash == log1.record_hash


def test_sec10_verify_chain_success_on_untampered_logs(db):
    """AuditService.verify_chain returns isValid=True for pristine hash chain."""
    result = AuditService.verify_chain(db)
    assert result["isValid"] is True
    assert result["verifiedCount"] >= 2


def test_sec10_verify_chain_detects_data_tampering(db):
    """Modifying record content directly in the database is detected by verify_chain."""
    log = AuditLog(
        id="audit-tamper-01",
        timestamp="2026-10-26T12:05:00Z",
        actor="Dr. Security Tester",
        actor_type="user",
        action="Legitimate Audit Entry",
        resource="Emergency #BL-102",
        resource_id="BL-102",
        status="success",
        module="blood",
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    # Malicious direct database tampering
    original_action = log.action
    log.action = "TAMPERED: Altered action description without updating hash"
    db.commit()

    try:
        verification = AuditService.verify_chain(db)
        assert verification["isValid"] is False
        assert verification["tamperedId"] == "audit-tamper-01"
        assert "Cryptographic integrity violation" in verification["error"]
    finally:
        # Restore original state
        log.action = original_action
        db.commit()
        db.delete(log)
        db.commit()


def test_sec10_verify_chain_detects_record_deletion(db):
    """Deleting an intermediate record in the hash chain is detected as a discontinuity."""
    # Create a 3-record sub-chain
    l1 = AuditLog(
        id="audit-chain-del-01",
        timestamp="2026-10-26T13:00:00Z",
        actor="System",
        actor_type="system",
        action="Chain L1",
        resource="Res1",
        status="success",
        module="system",
    )
    l2 = AuditLog(
        id="audit-chain-del-02",
        timestamp="2026-10-26T13:01:00Z",
        actor="System",
        actor_type="system",
        action="Chain L2",
        resource="Res2",
        status="success",
        module="system",
    )
    l3 = AuditLog(
        id="audit-chain-del-03",
        timestamp="2026-10-26T13:02:00Z",
        actor="System",
        actor_type="system",
        action="Chain L3",
        resource="Res3",
        status="success",
        module="system",
    )
    db.add_all([l1, l2, l3])
    db.commit()

    # Delete intermediate record l2
    db.delete(l2)
    db.commit()

    try:
        verification = AuditService.verify_chain(db)
        assert verification["isValid"] is False
        assert verification["tamperedId"] == "audit-chain-del-03"
        assert "Chain discontinuity" in verification["error"]
    finally:
        db.delete(l1)
        db.delete(l3)
        db.commit()


def test_sec10_legacy_unhashed_logs_do_not_break_verification(db):
    """Historical records created before hash chaining (record_hash is None) are preserved."""
    from sqlalchemy import text

    legacy = AuditLog(
        id="audit-legacy-001",
        timestamp="2026-01-01T00:00:00Z",
        actor="Legacy Importer",
        actor_type="system",
        action="Pre-chaining migration record",
        resource="Database",
        status="success",
        module="system",
    )
    db.add(legacy)
    db.commit()

    # Simulate pre-existing legacy record by clearing hashes directly in DB
    db.execute(text("UPDATE audit_logs SET record_hash = NULL, previous_hash = NULL WHERE id = 'audit-legacy-001'"))
    db.commit()
    db.refresh(legacy)

    assert legacy.record_hash is None
    assert legacy.previous_hash is None

    try:
        # Verification skips legacy logs without error
        res = AuditService.verify_chain(db)
        assert res["isValid"] is True
    finally:
        db.delete(legacy)
        db.commit()


def test_sec10_audit_verify_endpoint(client, doctor_token):
    """GET /api/v1/audit/verify endpoint allows authorized staff to inspect audit trail integrity."""
    resp = client.get("/api/v1/audit/verify", headers={"Authorization": f"Bearer {doctor_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "isValid" in data
    assert "verifiedCount" in data
