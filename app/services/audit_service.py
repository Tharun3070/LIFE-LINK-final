import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.audit import AuditLog, compute_audit_hash, GENESIS_HASH
from app.schemas.audit import AuditLogResponse, AuditLogCreate


class AuditService:
    @staticmethod
    def _map_log_to_response(log: AuditLog) -> AuditLogResponse:
        meta = None
        if log.metadata_json:
            try:
                meta = json.loads(log.metadata_json)
            except Exception:
                pass

        return AuditLogResponse(
            id=log.id,
            timestamp=log.timestamp,
            actor=log.actor,
            actorType=log.actor_type,
            action=log.action,
            resource=log.resource,
            resourceId=log.resource_id,
            authorization=log.authorization,
            status=log.status,
            module=log.module,
            ipAddress=log.ip_address,
            sessionId=log.session_id,
            metadata=meta,
            previousHash=log.previous_hash,
            recordHash=log.record_hash,
        )

    @staticmethod
    def get_logs(
        db: Session,
        module: Optional[str] = None,
        status_filter: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[AuditLogResponse]:
        query = db.query(AuditLog)
        if module and module != "all":
            query = query.filter(AuditLog.module == module)
        if status_filter and status_filter != "all":
            query = query.filter(AuditLog.status == status_filter)
        if search:
            s = f"%{search.lower()}%"
            query = query.filter(
                (AuditLog.action.ilike(s)) |
                (AuditLog.actor.ilike(s)) |
                (AuditLog.resource.ilike(s))
            )
        logs = query.order_by(AuditLog.timestamp.desc()).all()
        return [AuditService._map_log_to_response(log) for log in logs]

    @staticmethod
    def get_by_id(db: Session, event_id: str) -> AuditLogResponse:
        log = db.query(AuditLog).filter(AuditLog.id == event_id).first()
        if not log:
            raise HTTPException(status_code=404, detail="Audit log event not found")
        return AuditService._map_log_to_response(log)

    @staticmethod
    def create_log(db: Session, data: AuditLogCreate) -> AuditLogResponse:
        now_str = datetime.now(timezone.utc).isoformat()
        log = AuditLog(
            id=f"audit-{int(datetime.now(timezone.utc).timestamp() * 1000) % 100000}",
            timestamp=now_str,
            actor=data.actor,
            actor_type=data.actorType,
            action=data.action,
            resource=data.resource,
            resource_id=data.resourceId,
            authorization=data.authorization,
            status=data.status,
            module=data.module,
            ip_address=data.ipAddress,
            session_id=data.sessionId,
            metadata_json=json.dumps(data.metadata) if data.metadata else None,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return AuditService._map_log_to_response(log)

    @staticmethod
    def verify_chain(db: Session) -> Dict[str, Any]:
        """
        Cryptographic verification of audit trail integrity (SEC-10).
        Verifies:
        1. Canonical hash correctness for every chained record.
        2. Sequence continuity (each record's previous_hash matches the prior record_hash).
        3. Backward compatibility with pre-chaining historical logs.
        Note: Detects application-level tampering, deletion, or injection;
        does not prevent direct storage alteration by a privileged database administrator.
        """
        logs = db.query(AuditLog).order_by(AuditLog.timestamp.asc(), AuditLog.id.asc()).all()
        expected_prev = None
        verified_count = 0

        for log in logs:
            if not log.record_hash:
                # Pre-chaining legacy log: preserved without breaking chain
                continue

            if expected_prev is None:
                expected_prev = log.previous_hash or GENESIS_HASH

            # 1. Continuity check
            if (log.previous_hash or GENESIS_HASH) != expected_prev:
                return {
                    "isValid": False,
                    "tamperedId": log.id,
                    "error": f"Chain discontinuity at record {log.id}: expected previous_hash {expected_prev}, found {log.previous_hash}",
                    "verifiedCount": verified_count,
                }

            # 2. Cryptographic payload digest check
            expected_hash = compute_audit_hash(
                previous_hash=log.previous_hash,
                id=log.id,
                timestamp=log.timestamp,
                actor=log.actor,
                actor_type=log.actor_type,
                action=log.action,
                resource=log.resource,
                resource_id=log.resource_id,
                status=log.status,
                module=log.module,
                ip_address=log.ip_address,
                session_id=log.session_id,
                metadata_json=log.metadata_json,
            )
            if log.record_hash != expected_hash:
                return {
                    "isValid": False,
                    "tamperedId": log.id,
                    "error": f"Cryptographic integrity violation at record {log.id}: stored hash {log.record_hash} does not match computed digest {expected_hash}",
                    "verifiedCount": verified_count,
                }

            expected_prev = log.record_hash
            verified_count += 1

        return {
            "isValid": True,
            "verifiedCount": verified_count,
            "lastHash": expected_prev,
            "details": f"Successfully verified integrity of {verified_count} cryptographically chained audit records.",
        }


audit_service = AuditService()
