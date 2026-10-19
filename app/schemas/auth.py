from typing import Optional, List
from pydantic import BaseModel, Field


class LoginCredentials(BaseModel):
    identifier: str = Field(..., description="Email or Username")
    password: str = Field(..., description="User Password")
    rememberMe: Optional[bool] = Field(False)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: Optional[str] = None


class UserProfileSchema(BaseModel):
    id: str
    name: str
    email: str
    role: str
    roleTitle: Optional[str] = None
    hospitalId: Optional[str] = None
    hospitalName: Optional[str] = None
    organization: Optional[str] = None
    permissions: List[str] = []
    avatar: Optional[str] = None
    isVerified: bool = True
    lastLogin: Optional[str] = None
    sessionStatus: str = "active"


class AuthSessionResponse(BaseModel):
    user: UserProfileSchema
    token: str
    refreshToken: Optional[str] = None
    expiresAt: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str
