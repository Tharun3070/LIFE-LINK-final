from typing import Optional, List
from pydantic import BaseModel, Field


class Coordinates(BaseModel):
    lat: float
    lng: float


class DonorResponse(BaseModel):
    id: str
    bloodGroup: str
    distanceKm: float
    etaMinutes: int
    eligibility: str
    eligibilityReason: Optional[str] = None
    responseProbability: int
    reliabilityScore: int
    reachabilityScore: int
    aiRank: int
    status: str
    locationConsentGranted: bool
    lastDonationDays: Optional[int] = None
    historicalAcceptanceRate: int
    contactedAt: Optional[str] = None
    respondedAt: Optional[str] = None
    coordinates: Optional[Coordinates] = None


class DonorSearchConfig(BaseModel):
    initialRadiusKm: float = 2.0
    currentRadiusKm: float = 5.0
    maxRadiusKm: float = 15.0
    expansionCount: int = 1
    expansionReason: Optional[str] = "Insufficient eligible responses within initial 2km radius."


class RankedDonorsResponse(BaseModel):
    donors: List[DonorResponse]
    searchConfig: DonorSearchConfig
    aiRecommendation: str


class DonorContactRequest(BaseModel):
    emergencyId: str


class DonorResponseRequest(BaseModel):
    status: str = Field(..., description="accepted, declined, en_route, unavailable")
    shareLocation: Optional[bool] = False


class DonorAvailabilityRequest(BaseModel):
    status: str = Field(..., description="available, unavailable, paused")


class DonorConsentResponse(BaseModel):
    liveLocation: bool
    emergencyCommunication: bool
    donationRequests: bool
    healthDataSharing: bool
    updatedAt: str


class DonorConsentUpdateRequest(BaseModel):
    liveLocation: Optional[bool] = None
    emergencyCommunication: Optional[bool] = None
    donationRequests: Optional[bool] = None
    healthDataSharing: Optional[bool] = None
