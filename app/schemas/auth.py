from typing import Optional, List, Any
from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator


class LoginCredentials(BaseModel):
    identifier: str = Field(..., description="Email, Username, or User ID")
    password: str = Field(..., description="User Password")
    rememberMe: Optional[bool] = Field(False)

    @model_validator(mode="before")
    @classmethod
    def resolve_identifier(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("identifier"):
                if data.get("email"):
                    data["identifier"] = data["email"]
                elif data.get("username"):
                    data["identifier"] = data["username"]
        return data


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Full Name")
    email: EmailStr = Field(..., description="Valid Email Address")
    password: str = Field(..., min_length=8, max_length=128, description="Account Password (min 8 characters)")
    role: Optional[str] = Field("patient", description="Public role: 'patient', 'doctor', 'ambulance_driver', or 'donor'")
    bloodGroup: Optional[str] = Field(None, description="Optional Blood Group (e.g. O+, A+, B-, etc.)")
    phone: Optional[str] = Field(None, description="Contact Phone Number")
    city: Optional[str] = Field(None, description="City / District")
    # Doctor specific fields
    medicalLicenseNumber: Optional[str] = Field(None, description="Medical council registration / license number")
    hospitalName: Optional[str] = Field(None, description="Hospital or clinic name")
    clinicName: Optional[str] = Field(None, description="Clinic name alias")
    # Driver specific fields
    drivingLicenseNumber: Optional[str] = Field(None, description="Commercial driving license number")
    vehicleId: Optional[str] = Field(None, description="Ambulance or vehicle identifier")
    organization: Optional[str] = Field(None, description="Hospital or ambulance service affiliation")

    @model_validator(mode="before")
    @classmethod
    def map_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Map doctor registration number aliases
            if not data.get("medicalLicenseNumber"):
                data["medicalLicenseNumber"] = (
                    data.get("medical_license_number")
                    or data.get("medicalRegistrationNumber")
                    or data.get("medical_registration_number")
                )
            # Map hospital name aliases
            if not data.get("hospitalName"):
                data["hospitalName"] = data.get("hospital_name") or data.get("clinicName") or data.get("clinic_name")
            # Map driver license aliases
            if not data.get("drivingLicenseNumber"):
                data["drivingLicenseNumber"] = data.get("driving_license_number") or data.get("drivingLicenceDetails")
            # Map vehicle ID aliases
            if not data.get("vehicleId"):
                data["vehicleId"] = data.get("vehicle_id") or data.get("ambulanceIdentifier")
            # Map organization / affiliation aliases
            if not data.get("organization"):
                data["organization"] = data.get("affiliation") or data.get("ambulanceServiceAffiliation")
        return data

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 2:
            raise ValueError("Name must be at least 2 characters long.")
        return s

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v.strip()) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return v


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
    verificationStatus: str = "approved"
    phone: Optional[str] = None
    lastLogin: Optional[str] = None
    sessionStatus: str = "active"


class VerificationDecisionRequest(BaseModel):
    status: str = Field(..., description="Decision status: 'approved' or 'rejected'")
    notes: Optional[str] = Field(None, description="Verification review notes or reason")

    @field_validator("status")
    @classmethod
    def validate_decision_status(cls, v: str) -> str:
        s = v.strip().lower()
        if s not in {"approved", "rejected"}:
            raise ValueError("Status must be either 'approved' or 'rejected'.")
        return s


class PendingVerificationUserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    roleTitle: Optional[str] = None
    phone: Optional[str] = None
    hospitalName: Optional[str] = None
    organization: Optional[str] = None
    medicalLicenseNumber: Optional[str] = None
    drivingLicenseNumber: Optional[str] = None
    vehicleId: Optional[str] = None
    verificationStatus: str
    verificationNotes: Optional[str] = None
    isVerified: bool = False
    createdAt: Optional[str] = None


class AuthSessionResponse(BaseModel):
    user: UserProfileSchema
    token: str
    refreshToken: Optional[str] = None
    expiresAt: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str

