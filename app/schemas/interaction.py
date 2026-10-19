from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict, AliasChoices


class ContactStatus(str, Enum):
    PENDING = "pending"
    ATTEMPTED = "attempted"
    DELIVERED = "delivered"
    FAILED = "failed"


class ContactChannel(str, Enum):
    SMS = "sms"
    PUSH = "push"
    CALL = "call"
    IN_APP = "in_app"


class ResponseStatus(str, Enum):
    PENDING = "pending"
    RESPONDED = "responded"
    NO_RESPONSE = "no_response"
    EXPIRED = "expired"


class AcceptanceStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    UNREACHABLE = "unreachable"


class CompletionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELED = "canceled"
    MEDICALLY_DEFERRED = "medically_deferred"
    DID_NOT_ARRIVE = "did_not_arrive"


class OutcomeSource(str, Enum):
    SYSTEM = "system"
    DISPATCHER_PORTAL = "dispatcher_portal"
    DONOR_APP = "donor_app"
    TELEPHONY_WEBHOOK = "telephony_webhook"
    BLOOD_BANK_PORTAL = "blood_bank_portal"
    TEST_FIXTURE = "test_fixture"


class DataProvenance(str, Enum):
    PRODUCTION = "production"
    SYNTHETIC_SIMULATION = "synthetic_simulation"
    TEST_FIXTURE = "test_fixture"


# --- Request DTOs ---

class CandidateSelectionRequest(BaseModel):
    emergencyId: str = Field(..., description="ID of the blood emergency")
    donorId: str = Field(..., description="ID of the candidate donor")
    distanceKm: Optional[float] = Field(None, ge=0.0, description="Override distance if specifically calculated, else donor.distance_km is used")
    etaMinutes: Optional[int] = Field(None, ge=0, description="Override estimated travel time in minutes")
    compatibilityMatchType: Optional[str] = Field("identical", description="identical, universal")
    isSynthetic: bool = Field(False, description="Must be true if generated for testing or simulated benchmarks")
    dataProvenance: DataProvenance = Field(DataProvenance.PRODUCTION, description="Origin of this interaction record")
    notes: Optional[str] = None


class ContactAttemptRequest(BaseModel):
    contactChannel: ContactChannel = Field(ContactChannel.SMS, description="Channel used to alert the donor")
    outcomeSource: OutcomeSource = Field(OutcomeSource.DISPATCHER_PORTAL, description="Origin reporting the attempt")
    notes: Optional[str] = None


class ContactDeliveredRequest(BaseModel):
    outcomeSource: OutcomeSource = Field(OutcomeSource.TELEPHONY_WEBHOOK, description="Carrier/push notification delivery confirmation")
    notes: Optional[str] = None


class DonorResponseRecordRequest(BaseModel):
    accepted: bool = Field(..., description="True if donor agreed to donate, False if declined")
    shareLocation: Optional[bool] = Field(False, description="Whether to grant real-time location consent for this emergency")
    rejectionReason: Optional[str] = Field(None, description="Reason if declined (optional)")
    outcomeSource: OutcomeSource = Field(OutcomeSource.DONOR_APP, description="Origin capturing response")
    notes: Optional[str] = None


class DonationCompletionRequest(BaseModel):
    completionStatus: CompletionStatus = Field(CompletionStatus.COMPLETED, description="Final clinical outcome")
    unitsDonated: Optional[int] = Field(1, ge=0, description="Units of blood drawn if completed")
    outcomeSource: OutcomeSource = Field(OutcomeSource.BLOOD_BANK_PORTAL, description="Staff or hospital portal logging collection")
    notes: Optional[str] = None


class ContactFailedRequest(BaseModel):
    failureReason: str = Field(..., description="Carrier failure, invalid number, or transmission timeout")
    outcomeSource: OutcomeSource = Field(OutcomeSource.TELEPHONY_WEBHOOK, description="Origin logging carrier failure")
    notes: Optional[str] = None


class ContactTimeoutRequest(BaseModel):
    timeoutReason: Optional[str] = Field("Response window elapsed without donor reply", description="Timeout rationale")
    outcomeSource: OutcomeSource = Field(OutcomeSource.SYSTEM, description="Origin logging response timeout")
    notes: Optional[str] = None


class InteractionCancellationRequest(BaseModel):
    cancellationReason: str = Field("Emergency resolved or cancelled by hospital", description="Reason for cancellation")
    outcomeSource: OutcomeSource = Field(OutcomeSource.DISPATCHER_PORTAL, description="Origin logging cancellation")
    notes: Optional[str] = None


# --- Response DTOs ---

class DonorInteractionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    emergencyId: str = Field(..., validation_alias=AliasChoices("emergency_id", "emergencyId"))
    donorId: str = Field(..., validation_alias=AliasChoices("donor_id", "donorId"))
    selectedAt: str = Field(..., validation_alias=AliasChoices("selected_at", "selectedAt"))

    # Snapshot features
    distanceKm: float = Field(..., validation_alias=AliasChoices("distance_km", "distanceKm"))
    etaMinutes: int = Field(..., validation_alias=AliasChoices("eta_minutes", "etaMinutes"))
    timeOfDayHours: float = Field(..., validation_alias=AliasChoices("time_of_day_hours", "timeOfDayHours"))
    dayOfWeek: int = Field(..., validation_alias=AliasChoices("day_of_week", "dayOfWeek"))
    emergencyPriority: str = Field(..., validation_alias=AliasChoices("emergency_priority", "emergencyPriority"))
    compatibilityMatchType: str = Field(..., validation_alias=AliasChoices("compatibility_match_type", "compatibilityMatchType"))
    donorAvailabilityAtSelection: str = Field(..., validation_alias=AliasChoices("donor_availability_at_selection", "donorAvailabilityAtSelection"))
    donorTotalPreviousDonations: int = Field(..., validation_alias=AliasChoices("donor_total_previous_donations", "donorTotalPreviousDonations"))
    donorDaysSinceLastDonation: Optional[int] = Field(None, validation_alias=AliasChoices("donor_days_since_last_donation", "donorDaysSinceLastDonation"))

    # Lifecycle state
    contactStatus: str = Field(..., validation_alias=AliasChoices("contact_status", "contactStatus"))
    contactChannel: Optional[str] = Field(None, validation_alias=AliasChoices("contact_channel", "contactChannel"))
    contactAttemptedAt: Optional[str] = Field(None, validation_alias=AliasChoices("contact_attempted_at", "contactAttemptedAt"))
    contactDeliveredAt: Optional[str] = Field(None, validation_alias=AliasChoices("contact_delivered_at", "contactDeliveredAt"))

    responseStatus: str = Field(..., validation_alias=AliasChoices("response_status", "responseStatus"))
    respondedAt: Optional[str] = Field(None, validation_alias=AliasChoices("responded_at", "respondedAt"))
    responseLatencySeconds: Optional[int] = Field(None, validation_alias=AliasChoices("response_latency_seconds", "responseLatencySeconds"))

    acceptanceStatus: str = Field(..., validation_alias=AliasChoices("acceptance_status", "acceptanceStatus"))
    rejectionReason: Optional[str] = Field(None, validation_alias=AliasChoices("rejection_reason", "rejectionReason"))

    completionStatus: str = Field(..., validation_alias=AliasChoices("completion_status", "completionStatus"))
    completedAt: Optional[str] = Field(None, validation_alias=AliasChoices("completed_at", "completedAt"))
    unitsDonated: Optional[int] = Field(None, validation_alias=AliasChoices("units_donated", "unitsDonated"))

    # Provenance
    outcomeSource: str = Field(..., validation_alias=AliasChoices("outcome_source", "outcomeSource"))
    dataProvenance: str = Field(..., validation_alias=AliasChoices("data_provenance", "dataProvenance"))
    isSynthetic: bool = Field(..., validation_alias=AliasChoices("is_synthetic", "isSynthetic"))
    notes: Optional[str] = None
    createdAt: str = Field(..., validation_alias=AliasChoices("created_at", "createdAt"))
    updatedAt: str = Field(..., validation_alias=AliasChoices("updated_at", "updatedAt"))


class InteractionListResponse(BaseModel):
    items: List[DonorInteractionResponse]
    total: int
    limit: int
    offset: int
