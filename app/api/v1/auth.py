from fastapi import APIRouter, Depends, Request, status, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.auth import (
    LoginCredentials,
    RegisterRequest,
    AuthSessionResponse,
    TokenResponse,
    RefreshTokenRequest,
    UserProfileSchema,
)
from app.services.auth_service import auth_service
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.core.rate_limiter import rate_limiter, get_client_ip

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="User Registration",
    description="Registers a new user account (donor or patient), initializes profile and privacy consent, and returns authentication session.",
)
def register(request_data: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    if settings.RATE_LIMIT_ENABLED:
        client_ip = get_client_ip(request)
        rate_key = f"auth:register:{client_ip}"
        allowed, count, retry_after = rate_limiter.check(rate_key, settings.RATE_LIMIT_REGISTER, db=db)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many registration attempts. Please try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )
    return auth_service.register(db, request_data, ip_address=ip)


@router.post(
    "/login",
    response_model=AuthSessionResponse,
    summary="User Login",
    description="Authenticates user credentials and issues JWT access and refresh tokens.",
)
def login(credentials: LoginCredentials, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    if settings.RATE_LIMIT_ENABLED:
        client_ip = get_client_ip(request)
        identifier_clean = credentials.identifier.strip().lower() if credentials.identifier else "unknown"
        rate_key = f"auth:login:{client_ip}:{identifier_clean}"
        allowed, count, retry_after = rate_limiter.check(rate_key, settings.RATE_LIMIT_LOGIN, db=db)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many login attempts. Please try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )
    return auth_service.login(db, credentials, ip_address=ip)


@router.get(
    "/me",
    response_model=UserProfileSchema,
    summary="Get Current User",
    description="Returns the profile and authorized permissions of the currently authenticated user.",
)
def get_me(current_user: UserProfileSchema = Depends(get_current_user)):
    return current_user


@router.post(
    "/logout",
    summary="User Logout",
    description="Invalidates current user session and creates an audit record.",
)
def logout(
    request: Request,
    current_user: UserProfileSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else None
    return auth_service.logout(db, current_user, ip_address=ip)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh Access Token",
    description="Issues a fresh JWT access token using a valid refresh token.",
)
def refresh_token(body: RefreshTokenRequest, request: Request, db: Session = Depends(get_db)):
    if settings.RATE_LIMIT_ENABLED:
        client_ip = get_client_ip(request)
        rate_key = f"auth:refresh:{client_ip}"
        allowed, count, retry_after = rate_limiter.check(rate_key, settings.RATE_LIMIT_REFRESH, db=db)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many token refresh requests. Please try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )
    return auth_service.refresh_token(db, body.refresh_token)


@router.get(
    "/permissions",
    summary="Get Current User Permissions",
    description="Returns the list of specific RBAC permission codes granted to the current user.",
)
def get_permissions(current_user: UserProfileSchema = Depends(get_current_user)):
    return {"permissions": current_user.permissions, "role": current_user.role}
