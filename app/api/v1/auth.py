from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.auth import LoginCredentials, AuthSessionResponse, TokenResponse, RefreshTokenRequest, UserProfileSchema
from app.services.auth_service import auth_service
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=AuthSessionResponse,
    summary="User Login",
    description="Authenticates user credentials and issues JWT access and refresh tokens.",
)
def login(credentials: LoginCredentials, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
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
def refresh_token(body: RefreshTokenRequest, db: Session = Depends(get_db)):
    return auth_service.refresh_token(db, body.refresh_token)


@router.get(
    "/permissions",
    summary="Get Current User Permissions",
    description="Returns the list of specific RBAC permission codes granted to the current user.",
)
def get_permissions(current_user: UserProfileSchema = Depends(get_current_user)):
    return {"permissions": current_user.permissions, "role": current_user.role}
