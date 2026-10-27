import uuid
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.donor import Donor
from app.models.consent import Consent
from app.schemas.auth import (
    LoginCredentials,
    RegisterRequest,
    AuthSessionResponse,
    UserProfileSchema,
    TokenResponse,
)
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
)
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
            verificationStatus=getattr(user, "verification_status", "approved") or "approved",
            phone=getattr(user, "phone", None),
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

    @staticmethod
    def register(db: Session, request: RegisterRequest, ip_address: Optional[str] = None) -> AuthSessionResponse:
        email = request.email.strip().lower()

        # 1. Email Uniqueness Check (case-insensitive)
        existing = db.query(User).filter(User.email.ilike(email)).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email address already exists.",
            )

        # 2. Prevent Privilege Escalation
        requested_role = (request.role or UserRole.PATIENT.value).strip().lower()
        allowed_public_roles = {
            UserRole.PATIENT.value,
            UserRole.DOCTOR.value,
            UserRole.AMBULANCE_DRIVER.value,
            UserRole.AMBULANCE_OPERATOR.value,
            UserRole.DONOR.value,
        }
        if requested_role not in allowed_public_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Registration with role '{requested_role}' is prohibited. Public self-registration is limited to patient, doctor, ambulance_driver, and donor.",
            )

        # Canonicalize ambulance operator/driver
        canonical_role = UserRole.AMBULANCE_DRIVER.value if requested_role == UserRole.AMBULANCE_OPERATOR.value else requested_role

        # 3. Secure Password Hashing
        hashed_pw = get_password_hash(request.password)

        # 4. Determine Verification Status & Role Titles
        user_id = f"usr-{uuid.uuid4().hex[:10]}"
        hospital_name = request.hospitalName or request.clinicName
        organization = request.organization or hospital_name
        medical_license = request.medicalLicenseNumber
        driving_license = request.drivingLicenseNumber
        vehicle_id = request.vehicleId

        if canonical_role == UserRole.DOCTOR.value:
            verification_status = "pending"
            is_verified = False
            role_title = "Medical Doctor / Physician"
        elif canonical_role in [UserRole.AMBULANCE_DRIVER.value, UserRole.AMBULANCE_OPERATOR.value]:
            verification_status = "pending"
            is_verified = False
            role_title = "Emergency Ambulance Driver / Paramedic"
        elif canonical_role == UserRole.PATIENT.value:
            verification_status = "not_required"
            is_verified = True
            role_title = "Registered Patient / Caregiver"
        else:  # donor
            verification_status = "not_required"
            is_verified = True
            role_title = "Registered Donor"

        user = User(
            id=user_id,
            name=request.name.strip(),
            email=email,
            hashed_password=hashed_pw,
            role=canonical_role,
            role_title=role_title,
            hospital_name=hospital_name,
            organization=organization,
            phone=request.phone,
            medical_license_number=medical_license,
            driving_license_number=driving_license,
            vehicle_id=vehicle_id,
            verification_status=verification_status,
            is_verified=is_verified,
            session_status="active",
            last_login=datetime.now(timezone.utc).isoformat(),
        )
        db.add(user)

        # 5. Create Profile Record if registering as Donor
        if canonical_role == UserRole.DONOR.value:
            blood_grp = (request.bloodGroup or "O+").upper().strip()
            valid_groups = {"O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"}
            if blood_grp not in valid_groups:
                blood_grp = "O+"

            donor_id = f"D-{uuid.uuid4().hex[:6].upper()}"
            donor = Donor(
                id=donor_id,
                user_id=user_id,
                blood_group=blood_grp,
                eligibility="eligible" if request.bloodGroup else "pending_review",
                status="available",
                location_consent_granted=False,
                data_provenance="production",
                is_synthetic=False,
            )
            db.add(donor)

        # 6. Initialize Default Privacy Consent Record
        consent = Consent(
            id=f"cns-{uuid.uuid4().hex[:10]}",
            user_id=user_id,
            live_location=False,
            emergency_communication=True,
            donation_requests=True,
            health_data_sharing=False,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        db.add(consent)

        # 7. Audit Log
        audit = AuditLog(
            id=f"audit-reg-{uuid.uuid4().hex[:10]}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=user.name,
            actor_type="user",
            action=f"User self-registered as {canonical_role} (verification status: {verification_status})",
            resource="Auth Service",
            resource_id=user.id,
            authorization=f"Role: {canonical_role}",
            status="success",
            module="auth",
            ip_address=ip_address,
        )
        db.add(audit)
        db.commit()
        db.refresh(user)

        # 8. Issue JWT Tokens for Immediate Login
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
            verificationStatus=user.verification_status,
            phone=user.phone,
            lastLogin=user.last_login,
            sessionStatus=user.session_status,
        )

        return AuthSessionResponse(
            user=user_profile,
            token=access_token,
            refreshToken=refresh_token,
            expiresAt=expires_at,
        )



auth_service = AuthService()
