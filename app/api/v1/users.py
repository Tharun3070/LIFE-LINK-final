from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import UserProfileSchema
from app.schemas.user import UserResponse
from app.core.dependencies import get_current_user, require_role
from app.core.permissions import UserRole, ROLE_PERMISSIONS
from app.services.audit_service import audit_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get User Profile",
    description="Returns the profile information of the logged-in user.",
)
def get_user_me(current_user: UserProfileSchema = Depends(get_current_user)):
    return current_user


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
    results = []
    for u in users:
        role_enum = UserRole(u.role) if u.role in [r.value for r in UserRole] else UserRole.DOCTOR
        permissions = [p.value for p in ROLE_PERMISSIONS.get(role_enum, [])]
        results.append(
            UserResponse(
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
                lastLogin=u.last_login,
                sessionStatus=u.session_status,
            )
        )
    return results


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
        lastLogin=u.last_login,
        sessionStatus=u.session_status,
    )
