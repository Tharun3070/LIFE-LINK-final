from typing import List, Optional, Callable
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import decode_token
from app.core.permissions import UserRole, Permission, ROLE_PERMISSIONS
from app.models.user import User
from app.schemas.auth import UserProfileSchema


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> UserProfileSchema:
    """Extracts and validates JWT Bearer token from the Authorization header."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not authorization:
        raise credentials_exception

    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise credentials_exception
    except Exception:
        raise credentials_exception

    payload = decode_token(token)
    if not payload:
        raise credentials_exception

    user_id = payload.get("sub")
    if not user_id:
        raise credentials_exception

    user_db = db.query(User).filter(User.id == user_id).first()
    if not user_db:
        raise credentials_exception

    if user_db.session_status != "active":
        raise credentials_exception

    role_val = user_db.role
    role_enum = UserRole(role_val) if role_val in [r.value for r in UserRole] else UserRole.DOCTOR
    permissions = [p.value for p in ROLE_PERMISSIONS.get(role_enum, [])]

    return UserProfileSchema(
        id=user_db.id,
        name=user_db.name,
        email=user_db.email,
        role=user_db.role,
        roleTitle=user_db.role_title,
        hospitalId=user_db.hospital_id,
        hospitalName=user_db.hospital_name,
        organization=user_db.organization,
        permissions=permissions,
        avatar=user_db.avatar,
        isVerified=user_db.is_verified,
        lastLogin=user_db.last_login,
        sessionStatus=user_db.session_status,
    )


def require_role(allowed_roles: List[UserRole]) -> Callable:
    """Dependency factory enforcing that the authenticated user possesses one of the allowed roles."""
    def role_checker(current_user: UserProfileSchema = Depends(get_current_user)) -> UserProfileSchema:
        role_strings = [r.value for r in allowed_roles]
        if current_user.role not in role_strings and current_user.role != UserRole.ADMIN.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden for role '{current_user.role}'. Required: {role_strings}",
            )
        return current_user
    return role_checker


def require_permission(required_permission: Permission) -> Callable:
    """Dependency factory enforcing that the authenticated user possesses a specific RBAC permission."""
    def permission_checker(current_user: UserProfileSchema = Depends(get_current_user)) -> UserProfileSchema:
        if required_permission.value not in current_user.permissions and current_user.role != UserRole.ADMIN.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: Missing '{required_permission.value}' permission",
            )
        return current_user
    return permission_checker


def get_optional_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[UserProfileSchema]:
    """Extracts user profile if valid Authorization header present; otherwise returns None."""
    if not authorization:
        return None
    try:
        return get_current_user(authorization=authorization, db=db)
    except HTTPException:
        return None
