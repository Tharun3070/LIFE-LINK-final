from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.donor import (
    DonorResponse,
    DonorConsentResponse,
    DonorConsentUpdateRequest,
    DonorAvailabilityRequest,
)
from app.schemas.auth import UserProfileSchema
from app.services.donor_service import donor_service
from app.core.dependencies import get_current_user, require_role
from app.core.permissions import UserRole

router = APIRouter(prefix="/donors", tags=["Donors"])


@router.get(
    "",
    response_model=List[DonorResponse],
    summary="List Registered Donors",
    description="Returns registered donors in the LifeLink network with role-aware privacy protection.",
)
def list_donors(
    blood_group: Optional[str] = None,
    status: Optional[str] = None,
    eligibility: Optional[str] = None,
    max_distance_km: Optional[float] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: UserProfileSchema = Depends(get_current_user),
):
    return donor_service.get_all(
        db=db,
        blood_group=blood_group,
        status=status,
        eligibility=eligibility,
        max_distance_km=max_distance_km,
        skip=skip,
        limit=limit,
        current_user=current_user,
    )


@router.get(
    "/me",
    response_model=DonorResponse,
    summary="Get My Donor Profile",
    description="Returns the logged-in donor's personal profile, reliability metrics, and active SOS status.",
)
def get_donor_me(
    current_user: UserProfileSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return donor_service.get_donor_me(db, current_user)


@router.get(
    "/me/consent",
    response_model=DonorConsentResponse,
    summary="Get Donor Consent Settings",
    description="Returns current privacy and data sharing consent toggles for the authenticated donor.",
)
def get_consent_me(
    current_user: UserProfileSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return donor_service.get_donor_consent(db, current_user)


@router.patch(
    "/me/consent",
    response_model=DonorConsentResponse,
    summary="Update Donor Consent",
    description="Updates live location, communication, and health data sharing consent.",
)
def update_consent_me(
    data: DonorConsentUpdateRequest,
    current_user: UserProfileSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return donor_service.update_donor_consent(db, data, current_user)


@router.post(
    "/me/availability",
    summary="Set Donor Availability",
    description="Updates active donor status (available, unavailable, paused).",
)
def set_availability(
    data: DonorAvailabilityRequest,
    current_user: UserProfileSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return donor_service.set_donor_availability(db, data, current_user)


@router.get(
    "/{donor_id}",
    response_model=DonorResponse,
    summary="Get Donor By ID",
    description="Returns profile details for a specific donor. Exact GPS coordinates require location consent.",
)
def get_donor_by_id(
    donor_id: str,
    db: Session = Depends(get_db),
    current_user: UserProfileSchema = Depends(get_current_user),
):
    return donor_service.get_by_id(db, donor_id, current_user)
