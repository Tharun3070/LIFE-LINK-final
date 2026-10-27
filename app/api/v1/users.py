from typing import List, Optional
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.models.audit import AuditLog
from app.schemas.auth import (
    UserProfileSchema,
    VerificationDecisionRequest,
    PendingVerificationUserResponse,
)
from app.schemas.user import UserResponse, UserUpdate
from app.core.dependencies import get_current_user, require_role
from app.core.permissions import UserRole, ROLE_PERMISSIONS
from app.services.audit_service import audit_service

router = APIRouter(prefix="/users", tags=["Users"])


def _map_user_to_response(u: User) -> UserResponse:
    role_enum = UserRole(u.role) if u.role in [r.value for r in UserRole] else UserRole.DOCTOR
    permissions = [p.value for p in ROLE_PERMISSIONS.get(role_enum, [])]
    return UserResponse(
        id=u.id,
        name=u.name,
        email=u.email,
        role=u.role,
        roleTitle=u.role_title,
        hospitalId=u.hospital_id,
        hospitalName=u.hospital_name,
        organization=u.organization,
        permissions=permissions,
        avatar=u.avatar,
        isVerified=u.is_verified,
        verificationStatus=getattr(u, "verification_status", "approved") or "approved",
        phone=getattr(u, "phone", None),
        lastLogin=u.last_login,
        sessionStatus=u.session_status,
    )


def _map_user_to_verification_response(u: User) -> PendingVerificationUserResponse:
    return PendingVerificationUserResponse(
        id=u.id,
        name=u.name,
        email=u.email,
        role=u.role,
        roleTitle=u.role_title,
        phone=u.phone,
        hospitalName=u.hospital_name,
        organization=u.organization,
        medicalLicenseNumber=u.medical_license_number,
        drivingLicenseNumber=u.driving_license_number,
        vehicleId=u.vehicle_id,
        verificationStatus=getattr(u, "verification_status", "approved") or "approved",
        verificationNotes=u.verification_notes,
        isVerified=u.is_verified,
        createdAt=u.created_at.isoformat() if u.created_at else None,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get User Profile",
    description="Returns the profile information of the logged-in user.",
)
def get_user_me(current_user: UserProfileSchema = Depends(get_current_user)):
    return current_user


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update User Profile",
    description="Updates non-privileged profile information. Role, verification status, and credentials cannot be altered here.",
)
def update_user_me(
    update_data: UserUpdate,
    current_user: UserProfileSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_db = db.query(User).filter(User.id == current_user.id).first()
    if not user_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if update_data.name is not None:
        user_db.name = update_data.name.strip()
    if update_data.avatar is not None:
        user_db.avatar = update_data.avatar
    if update_data.phone is not None:
        user_db.phone = update_data.phone.strip()
    if update_data.roleTitle is not None:
        user_db.role_title = update_data.roleTitle
    if update_data.hospitalName is not None:
        user_db.hospital_name = update_data.hospitalName
    if update_data.organization is not None:
        user_db.organization = update_data.organization

    user_db.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user_db)
    return _map_user_to_response(user_db)


@router.get(
    "/me/permissions",
    summary="Get User Permissions",
    description="Returns the list of permissions granted to the current user.",
)
def get_user_me_permissions(current_user: UserProfileSchema = Depends(get_current_user)):
    return {"permissions": current_user.permissions, "role": current_user.role}


@router.get(
    "/me/activity",
    summary="Get User Activity",
    description="Returns the recent audit logs and actions performed by the current user.",
)
def get_user_me_activity(
    current_user: UserProfileSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return audit_service.get_logs(db, search=current_user.name)


@router.get(
    "/pending-verification",
    response_model=List[PendingVerificationUserResponse],
    summary="List Pending Verifications (Admin only)",
    description="Administrative endpoint to inspect doctors and ambulance drivers awaiting credential verification.",
)
def list_pending_verifications(
    db: Session = Depends(get_db),
    admin_user: UserProfileSchema = Depends(require_role([UserRole.ADMIN])),
):
    pending_users = db.query(User).filter(User.verification_status == "pending").all()
    return [_map_user_to_verification_response(u) for u in pending_users]


@router.get(
    "/{user_id}/verification",
    response_model=PendingVerificationUserResponse,
    summary="Get User Verification Details (Admin only)",
    description="Administrative endpoint to inspect verification credentials for a specific professional user.",
)
def get_user_verification_detail(
    user_id: str,
    db: Session = Depends(get_db),
    admin_user: UserProfileSchema = Depends(require_role([UserRole.ADMIN])),
):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{user_id}' not found")
    return _map_user_to_verification_response(u)


@router.post(
    "/{user_id}/verify",
    response_model=PendingVerificationUserResponse,
    summary="Verify User Account (Admin only)",
    description="Administrative endpoint to approve or reject professional verification for doctors or ambulance drivers.",
)
def verify_user_account(
    user_id: str,
    decision: VerificationDecisionRequest,
    db: Session = Depends(get_db),
    admin_user: UserProfileSchema = Depends(require_role([UserRole.ADMIN])),
):
    # Prevent self-verification: an administrator cannot approve or reject their own account
    if admin_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot approve, reject, or modify their own verification status.",
        )

    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{user_id}' not found")

    decision_status = decision.status.strip().lower()
    if decision_status not in {"approved", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid verification decision status '{decision.status}'. Must be 'approved' or 'rejected'.",
        )

    now = datetime.now(timezone.utc)
    u.verification_status = decision_status
    u.is_verified = (decision_status == "approved")
    u.verification_notes = decision.notes
    u.verified_at = now
    u.verified_by = admin_user.id
    u.updated_at = now

    audit = AuditLog(
        id=f"audit-verify-{uuid.uuid4().hex[:10]}",
        timestamp=now.isoformat(),
        actor=admin_user.name,
        actor_type="admin",
        action=f"Professional account {u.email} ({u.role}) verification set to '{decision_status}'",
        resource="User Verification",
        resource_id=u.id,
        authorization=f"Admin: {admin_user.id}",
        status="success",
        module="admin_rbac",
    )
    db.add(audit)
    db.commit()
    db.refresh(u)

    return _map_user_to_verification_response(u)


@router.post(
    "/{user_id}/approve",
    response_model=PendingVerificationUserResponse,
    summary="Approve Professional Account (Admin only)",
    description="Convenience administrative endpoint to approve a doctor or ambulance driver account.",
)
def approve_user_account(
    user_id: str,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    admin_user: UserProfileSchema = Depends(require_role([UserRole.ADMIN])),
):
    decision = VerificationDecisionRequest(status="approved", notes=notes)
    return verify_user_account(user_id=user_id, decision=decision, db=db, admin_user=admin_user)


@router.post(
    "/{user_id}/reject",
    response_model=PendingVerificationUserResponse,
    summary="Reject Professional Account (Admin only)",
    description="Convenience administrative endpoint to reject a doctor or ambulance driver account.",
)
def reject_user_account(
    user_id: str,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    admin_user: UserProfileSchema = Depends(require_role([UserRole.ADMIN])),
):
    decision = VerificationDecisionRequest(status="rejected", notes=notes)
    return verify_user_account(user_id=user_id, decision=decision, db=db, admin_user=admin_user)


@router.get(
    "",
    response_model=List[UserResponse],
    summary="List Platform Users (Admin only)",
    description="Administrative endpoint to inspect all registered users across the healthcare network.",
)
def list_users(
    db: Session = Depends(get_db),
    admin_user: UserProfileSchema = Depends(require_role([UserRole.ADMIN])),
):
    users = db.query(User).all()
    return [_map_user_to_response(u) for u in users]


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get User By ID (Admin only)",
    description="Administrative endpoint to retrieve user details by ID.",
)
def get_user_by_id(
    user_id: str,
    db: Session = Depends(get_db),
    admin_user: UserProfileSchema = Depends(require_role([UserRole.ADMIN])),
):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _map_user_to_response(u)

