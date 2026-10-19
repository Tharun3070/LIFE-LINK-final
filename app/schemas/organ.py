from typing import Optional
from pydantic import BaseModel, Field
from app.schemas.donor import Coordinates


class OrganResponse(BaseModel):
    id: str
    organType: str
    sourceHospitalId: str
    sourceHospitalName: str
    distanceKm: float
    etaMinutes: int
    viabilityRemainingSeconds: int
    viabilityTotalSeconds: int
    viabilityLevel: str # normal, warning, critical
    reachabilityScore: int
    aiRecommendation: str # proceed, caution, do_not_proceed
    aiRationale: str
    status: str # available, clinical_review, allocated, en_route, transplanted, expired, rejected
    clinicalReviewStatus: str # pending, in_review, approved, rejected, not_required
    authorizedCoordinatorId: Optional[str] = None
    coordinates: Optional[Coordinates] = None
    availableAt: str
    updatedAt: str


class ClinicalReviewRequest(BaseModel):
    decision: Optional[str] = Field("approved", description="approved, rejected, in_review")
    notes: Optional[str] = None
    coordinatorId: Optional[str] = None


class OrganRequest(BaseModel):
    organType: str
    recipientHospitalId: str
    urgency: Optional[str] = "critical"
    notes: Optional[str] = None


class OrganRequestResponse(BaseModel):
    id: str
    emergencyId: str
    status: str
    organType: str
    recipientHospitalId: str
    recipientHospitalName: str
    urgency: str
    priority: str
    createdAt: str
    notes: Optional[str] = None
    eta: Optional[int] = None

