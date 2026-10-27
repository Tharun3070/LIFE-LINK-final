from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict, AliasChoices


class Coordinates(BaseModel):
    lat: float
    lng: float


class DonorResponse(BaseModel):
    id: str
    bloodGroup: str
    distanceKm: Optional[float] = None
    etaMinutes: Optional[int] = None
    straightLineDistanceKm: Optional[float] = None
    roadDistanceKm: Optional[float] = None
    distanceSource: Optional[str] = None
    etaSource: Optional[str] = None
    isLiveEstimate: Optional[bool] = False
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
    name: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    pincode: Optional[str] = None



class DonorSearchConfig(BaseModel):
    initialRadiusKm: float = 2.0
    currentRadiusKm: float = 2.0
    maxRadiusKm: float = 20.0
    expansionCount: int = 0
    expansionReason: Optional[str] = "Candidates matched within initial 2.0km search radius."


class RankedDonorsResponse(BaseModel):
    donors: List[DonorResponse]
    searchConfig: DonorSearchConfig
    aiRecommendation: str
    unlocalizedDonors: Optional[List[DonorResponse]] = None


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


class AcceptedDonorRankingEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    donorId: str = Field(..., validation_alias=AliasChoices("donor_id", "donorId"), description="Unique donor identifier")
    bloodGroup: str = Field(..., validation_alias=AliasChoices("blood_group", "bloodGroup"), description="Donor ABO/Rh blood group")
    acceptanceStatus: str = Field("accepted", validation_alias=AliasChoices("acceptance_status", "acceptanceStatus"), description="Explicit acceptance status")
    acceptedAt: Optional[str] = Field(None, validation_alias=AliasChoices("accepted_at", "acceptedAt"), description="ISO timestamp when donor accepted the request")
    routeDistanceKm: Optional[float] = Field(None, validation_alias=AliasChoices("route_distance_km", "routeDistanceKm", "distance_km", "distanceKm"), description="Estimated road route distance in kilometers")
    estimatedTravelDurationMinutes: Optional[int] = Field(None, validation_alias=AliasChoices("estimated_travel_duration_minutes", "estimatedTravelDurationMinutes", "eta_minutes", "etaMinutes"), description="Estimated travel duration to receiving hospital in minutes")
    etaCalculationMethod: str = Field(..., validation_alias=AliasChoices("eta_calculation_method", "etaCalculationMethod"), description="Method used to calculate ETA ('google_maps_live', 'simulated_heuristic_fallback', 'unavailable_missing_coordinates')")
    isLiveEstimate: bool = Field(..., validation_alias=AliasChoices("is_live_estimate", "isLiveEstimate", "is_live_traffic", "isLiveTraffic"), description="True if computed using live Google Maps traffic; False if heuristic fallback")
    etaAvailable: bool = Field(..., validation_alias=AliasChoices("eta_available", "etaAvailable"), description="True if ETA could be reliably computed; False if coordinates or routing unavailable")
    transitStatusNote: str = Field(
        "Donor has explicitly accepted emergency request; physical transit has not begun",
        validation_alias=AliasChoices("transit_status_note", "transitStatusNote"),
        description="Clinical transit note preventing false assumption that donor is en route"
    )


class EmergencyAcceptedDonorsRankingResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    emergencyId: str = Field(..., validation_alias=AliasChoices("emergency_id", "emergencyId"), description="Blood emergency ID")
    destinationHospitalId: str = Field(..., validation_alias=AliasChoices("destination_hospital_id", "destinationHospitalId"), description="Receiving hospital ID")
    destinationHospitalName: Optional[str] = Field(None, validation_alias=AliasChoices("destination_hospital_name", "destinationHospitalName"), description="Receiving hospital name")
    rankingGeneratedAt: str = Field(..., validation_alias=AliasChoices("ranking_generated_at", "rankingGeneratedAt"), description="ISO timestamp when ranking was computed")
    totalAcceptedDonors: int = Field(..., validation_alias=AliasChoices("total_accepted_donors", "totalAcceptedDonors", "accepted_donors_count", "acceptedDonorsCount"), description="Total count of accepted donors evaluated")
    rankedDonors: List[AcceptedDonorRankingEntry] = Field(..., validation_alias=AliasChoices("ranked_donors", "rankedDonors"), description="Donors ranked by estimated arrival time from shortest to longest")


class ContactedDonorSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    donorId: str = Field(..., validation_alias=AliasChoices("donor_id", "donorId"))
    bloodGroup: str = Field(..., validation_alias=AliasChoices("blood_group", "bloodGroup"))
    distanceKm: Optional[float] = Field(None, validation_alias=AliasChoices("distance_km", "distanceKm"))
    contactedAt: str = Field(..., validation_alias=AliasChoices("contacted_at", "contactedAt"))
    testContactPhone: Optional[str] = Field(None, validation_alias=AliasChoices("test_contact_phone", "testContactPhone"))


class DonorBatchDispatchResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    emergencyId: str = Field(..., validation_alias=AliasChoices("emergency_id", "emergencyId"))
    batchNumber: int = Field(..., validation_alias=AliasChoices("batch_number", "batchNumber"))
    donorsContactedCount: int = Field(..., validation_alias=AliasChoices("donors_contacted_count", "donorsContactedCount"))
    contactedDonors: List[ContactedDonorSummary] = Field(default_factory=list, validation_alias=AliasChoices("contacted_donors", "contactedDonors"))
    currentRadiusKm: float = Field(..., validation_alias=AliasChoices("current_radius_km", "currentRadiusKm"))
    expansionCount: int = Field(0, validation_alias=AliasChoices("expansion_count", "expansionCount"))
    acceptedDonorsCount: int = Field(..., validation_alias=AliasChoices("accepted_donors_count", "acceptedDonorsCount"))
    targetAcceptedDonors: int = Field(3, validation_alias=AliasChoices("target_accepted_donors", "targetAcceptedDonors"))
    targetReached: bool = Field(..., validation_alias=AliasChoices("target_reached", "targetReached"))
    message: str


class DonorWorkflowStatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    emergencyId: str = Field(..., validation_alias=AliasChoices("emergency_id", "emergencyId"))
    totalContacted: int = Field(..., validation_alias=AliasChoices("total_contacted", "totalContacted"))
    totalAccepted: int = Field(..., validation_alias=AliasChoices("total_accepted", "totalAccepted"))
    totalDeclined: int = Field(..., validation_alias=AliasChoices("total_declined", "totalDeclined"))
    totalPending: int = Field(..., validation_alias=AliasChoices("total_pending", "totalPending"))
    targetAcceptedDonors: int = Field(3, validation_alias=AliasChoices("target_accepted_donors", "targetAcceptedDonors"))
    targetReached: bool = Field(..., validation_alias=AliasChoices("target_reached", "targetReached"))
    currentRadiusKm: float = Field(..., validation_alias=AliasChoices("current_radius_km", "currentRadiusKm"))
    canExpandRadius: bool = Field(..., validation_alias=AliasChoices("can_expand_radius", "canExpandRadius"))

