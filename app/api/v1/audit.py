from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.audit import AuditLogResponse
from app.schemas.auth import UserProfileSchema
from app.services.audit_service import audit_service
from app.core.dependencies import get_current_user, require_permission
from app.core.permissions import Permission

router = APIRouter(prefix="/audit", tags=["Audit & Governance"])


@router.get(
    "",
    response_model=List[AuditLogResponse],
    summary="List Audit Logs",
    description="Returns immutable system, AI, and user action audit records (Filterable by module, status, search).",
)
def list_audit_logs(
    module: Optional[str] = Query(None, description="Module filter (blood, organ, ambulance, system, auth)"),
    status: Optional[str] = Query(None, description="Status filter (success, failed, pending)"),
    search: Optional[str] = Query(None, description="Search query across actors, actions, and resources"),
    db: Session = Depends(get_db),
    current_user: UserProfileSchema = Depends(require_permission(Permission.VIEW_AUDIT_LOGS)),
):
    return audit_service.get_logs(db, module=module, status_filter=status, search=search)


@router.get(
    "/verify",
    summary="Verify Audit Trail Cryptographic Integrity",
    description="Traverses the cryptographic hash chain of audit records to verify continuity and detect unauthorized tampering or omissions.",
)
def verify_audit_chain(
    db: Session = Depends(get_db),
    current_user: UserProfileSchema = Depends(require_permission(Permission.VIEW_AUDIT_LOGS)),
):
    return audit_service.verify_chain(db)


@router.get(
    "/{event_id}",
    response_model=AuditLogResponse,
    summary="Get Audit Event Details",
    description="Retrieves a single tamper-evident audit record by ID.",
)
def get_audit_log(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: UserProfileSchema = Depends(require_permission(Permission.VIEW_AUDIT_LOGS)),
):
    return audit_service.get_by_id(db, event_id)
