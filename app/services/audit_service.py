import json
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.audit import AuditLog
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


audit_service = AuditService()
