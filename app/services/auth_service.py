import uuid
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.user import User
from app.schemas.auth import LoginCredentials, AuthSessionResponse, UserProfileSchema, TokenResponse
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.core.permissions import UserRole, ROLE_PERMISSIONS
from app.core.config import settings
from app.models.audit import AuditLog


class AuthService:
    # Pre-computed bcrypt hash for constant-time comparison on unknown user
    DUMMY_BCRYPT_HASH = "$2b$12$JIdh7oxO.jauf2ckaIVl6e3g2ZNWoUbkI7DBUj7JW2ilkCqc.5V2i"

    @staticmethod
    def login(db: Session, credentials: LoginCredentials, ip_address: Optional[str] = None) -> AuthSessionResponse:
        identifier = credentials.identifier.strip()

        # 1. Look up user strictly by exact email (case-insensitive) or exact user ID
        user = db.query(User).filter(
            (User.email.ilike(identifier)) | (User.id == identifier)
        ).first()

        # 2. Timing attack & account enumeration mitigation: verify against dummy hash if user not found
        if not user:
            verify_password(credentials.password, AuthService.DUMMY_BCRYPT_HASH)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 3. Verify password
        if not verify_password(credentials.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 4. Update last login
        user.last_login = datetime.now(timezone.utc).isoformat()
        user.session_status = "active"
        db.commit()
        db.refresh(user)

        # 5. Create audit log
        audit = AuditLog(
            id=f"audit-login-{uuid.uuid4().hex[:10]}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=user.name,
            actor_type="user",
            action=f"User login successful ({user.role})",
            resource="Auth Service",
            resource_id=user.id,
            authorization=f"Role: {user.role}",
            status="success",
            module="auth",
            ip_address=ip_address,
        )
        db.add(audit)
        db.commit()

        # 6. Issue tokens
        access_token = create_access_token(subject=user.id, role=user.role)
        refresh_token = create_refresh_token(subject=user.id, role=user.role)
        expires_at = int(datetime.now(timezone.utc).timestamp()) + (settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)

        role_enum = UserRole(user.role) if user.role in [r.value for r in UserRole] else UserRole.DOCTOR
        permissions = [p.value for p in ROLE_PERMISSIONS.get(role_enum, [])]

        user_profile = UserProfileSchema(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
            roleTitle=user.role_title,
            hospitalId=user.hospital_id,
            hospitalName=user.hospital_name,
            organization=user.organization,
            permissions=permissions,
            avatar=user.avatar,
            isVerified=user.is_verified,
            lastLogin=user.last_login,
            sessionStatus=user.session_status,
        )

        return AuthSessionResponse(
            user=user_profile,
            token=access_token,
            refreshToken=refresh_token,
            expiresAt=expires_at,
        )

    @staticmethod
    def refresh_token(db: Session, refresh_token_str: str) -> TokenResponse:
        payload = decode_token(refresh_token_str)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )
        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if user.session_status != "active":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session is inactive or logged out",
                headers={"WWW-Authenticate": "Bearer"},
            )

        new_access_token = create_access_token(subject=user.id, role=user.role)
        new_refresh_token = create_refresh_token(subject=user.id, role=user.role)
        expires_in = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

        return TokenResponse(
            access_token=new_access_token,
            token_type="bearer",
            expires_in=expires_in,
            refresh_token=new_refresh_token,
        )

    @staticmethod
    def logout(db: Session, current_user: UserProfileSchema, ip_address: Optional[str] = None) -> dict:
        user = db.query(User).filter(User.id == current_user.id).first()
        if user:
            user.session_status = "inactive"
            db.commit()

        audit = AuditLog(
            id=f"audit-logout-{uuid.uuid4().hex[:10]}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=current_user.name,
            actor_type="user",
            action="User logged out",
            resource="Auth Service",
            resource_id=current_user.id,
            authorization=f"Role: {current_user.role}",
            status="success",
            module="auth",
            ip_address=ip_address,
        )
        db.add(audit)
        db.commit()

        return {"message": "Logged out successfully"}


auth_service = AuthService()
