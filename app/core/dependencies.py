from typing import List, Optional, Callable, Union
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import decode_token
from app.core.permissions import UserRole, Permission, ROLE_PERMISSIONS
from app.models.user import User
from app.schemas.auth import UserProfileSchema

bearer_scheme = HTTPBearer(auto_error=False)

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> UserProfileSchema:
    """Extract and validate a JWT Bearer token from the Authorization header."""

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise credentials_exception

    token = credentials.credentials

    payload = decode_token(token)
    if not payload:
        raise credentials_exception

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type: Expected access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise credentials_exception

    user_db = db.query(User).filter(User.id == user_id).first()
    if not user_db:
        raise credentials_exception

    if user_db.session_status != "active":
        raise credentials_exception

    role_val = user_db.role
    role_enum = (
        UserRole(role_val)
        if role_val in [r.value for r in UserRole]
        else UserRole.DOCTOR
    )
    permissions = [
        p.value for p in ROLE_PERMISSIONS.get(role_enum, [])
    ]

    verification_status = getattr(user_db, "verification_status", "approved") or "approved"

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
        verificationStatus=verification_status,
        phone=getattr(user_db, "phone", None),
        lastLogin=user_db.last_login,
        sessionStatus=user_db.session_status,
    )

def require_role(allowed_roles: Union[List[Union[UserRole, str]], UserRole, str]) -> Callable:
    """Dependency factory enforcing that the authenticated user possesses one of the allowed roles and required verification."""
    if not isinstance(allowed_roles, list):
        roles_list = [allowed_roles]
    else:
        roles_list = allowed_roles

    role_strings = [r.value if isinstance(r, UserRole) else str(r) for r in roles_list]

    # Interoperability: ambulance_operator and ambulance_driver can access the same driver features
    if UserRole.AMBULANCE_OPERATOR.value in role_strings or UserRole.AMBULANCE_DRIVER.value in role_strings:
        if UserRole.AMBULANCE_OPERATOR.value not in role_strings:
            role_strings.append(UserRole.AMBULANCE_OPERATOR.value)
        if UserRole.AMBULANCE_DRIVER.value not in role_strings:
            role_strings.append(UserRole.AMBULANCE_DRIVER.value)

    def role_checker(current_user: UserProfileSchema = Depends(get_current_user)) -> UserProfileSchema:
        if current_user.role not in role_strings and current_user.role != UserRole.ADMIN.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden for role '{current_user.role}'. Required: {role_strings}",
            )

        # Enforce verification approval for professional accounts (doctor, ambulance drivers/operators)
        if current_user.role in [UserRole.DOCTOR.value, UserRole.AMBULANCE_OPERATOR.value, UserRole.AMBULANCE_DRIVER.value]:
            if current_user.verificationStatus == "rejected":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Professional account has been rejected by administration.",
                )
            if current_user.verificationStatus == "pending" or not current_user.isVerified:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Professional account pending verification. Please await administrator approval.",
                )

        return current_user

    return role_checker


require_roles = require_role


def require_verified_user(current_user: UserProfileSchema = Depends(get_current_user)) -> UserProfileSchema:
    """Enforces that the authenticated user account is verified and approved."""
    if current_user.role in [UserRole.DOCTOR.value, UserRole.AMBULANCE_OPERATOR.value, UserRole.AMBULANCE_DRIVER.value]:
        if current_user.verificationStatus == "rejected":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Professional account has been rejected by administration.",
            )
        if current_user.verificationStatus == "pending" or not current_user.isVerified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Professional account pending verification. Please await administrator approval.",
            )
    elif current_user.verificationStatus == "rejected":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been rejected by administration.",
        )
    return current_user


def require_permission(required_permission: Permission) -> Callable:
    """Dependency factory enforcing that the authenticated user possesses a specific RBAC permission."""
    def permission_checker(current_user: UserProfileSchema = Depends(get_current_user)) -> UserProfileSchema:
        if required_permission.value not in current_user.permissions and current_user.role != UserRole.ADMIN.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: Missing '{required_permission.value}' permission",
            )

        # Enforce verification approval for professional accounts exercising permissions
        if current_user.role in [UserRole.DOCTOR.value, UserRole.AMBULANCE_OPERATOR.value, UserRole.AMBULANCE_DRIVER.value]:
            if current_user.verificationStatus == "rejected":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Professional account has been rejected by administration.",
                )
            if current_user.verificationStatus == "pending" or not current_user.isVerified:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Professional account pending verification. Please await administrator approval.",
                )

        return current_user
    return permission_checker




def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> Optional[UserProfileSchema]:
    """Return the current user when a valid Bearer token is provided."""

    if credentials is None:
        return None

    try:
        return get_current_user(
            credentials=credentials,
            db=db,
        )
    except HTTPException:
        return None