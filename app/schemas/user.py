from typing import Optional, List
from pydantic import BaseModel, EmailStr
from app.schemas.auth import UserProfileSchema


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str
    roleTitle: Optional[str] = None
    hospitalId: Optional[str] = None
    hospitalName: Optional[str] = None
    organization: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    roleTitle: Optional[str] = None
    hospitalName: Optional[str] = None
    organization: Optional[str] = None
    avatar: Optional[str] = None
    phone: Optional[str] = None



class UserResponse(UserProfileSchema):
    pass
