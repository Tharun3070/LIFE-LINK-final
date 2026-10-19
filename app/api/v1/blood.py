from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.emergency import EmergencyResponse, EmergencyCreate, BloodEmergencyRequest
from app.schemas.donor import (
    RankedDonorsResponse,
    DonorContactRequest,
    DonorResponseRequest,
)
from app.schemas.auth import UserProfileSchema
from app.services.emergency_service import emergency_service
from app.services.donor_service import donor_service
from app.core.dependencies import get_current_user, require_role, get_optional_current_user
from app.core.permissions import UserRole

router = APIRouter(prefix="/blood", tags=["Blood Module"])


@router.post(
    "/emergency",
    response_model=EmergencyResponse,
    summary="Create Blood Emergency (Frontend Compatible)",
    description="Initiates a blood emergency SOS request.",
)
@router.post(
    "/requests",
    response_model=EmergencyResponse,
    summary="Create Blood Emergency Request",
    description="Creates a new blood request and triggers AI intent parsing and donor search.",
)
def create_blood_emergency(
    req: BloodEmergencyRequest,
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.DOCTOR, UserRole.HOSPITAL_STAFF, UserRole.ADMIN
    ])),
    db: Session = Depends(get_db),
):
    create_dto = EmergencyCreate(
        type="blood",
        priority=req.priority,
        hospitalId=req.hospitalId,
        description=f"Blood emergency — {req.bloodGroup}, {req.unitsRequired} units ({req.notes or 'Urgent transfusion'})",
        bloodGroup=req.bloodGroup,
        unitsRequired=req.unitsRequired,
    )
    return emergency_service.create(db, create_dto, current_user)


@router.get(
    "/requests",
    response_model=List[EmergencyResponse],
    summary="List Blood Emergency Requests",
    description="Lists all active blood requests.",
)
def list_blood_requests(db: Session = Depends(get_db)):
    all_emergencies = emergency_service.get_all(db)
    return [e for e in all_emergencies if e.type == "blood"]


@router.get(
    "/donors/ranked",
    response_model=RankedDonorsResponse,
    summary="Get AI-Ranked Donors",
    description="Returns candidate donors ranked by reachability, reliability, and ETA.",
)
def get_ranked_donors(
    emergencyId: str = Query(..., description="ID of the active blood emergency"),
    db: Session = Depends(get_db),
    current_user: Optional[UserProfileSchema] = Depends(get_optional_current_user),
):
    return donor_service.get_ranked_donors(db, emergency_id=emergencyId, current_user=current_user)


@router.post(
    "/donors/{donor_id}/contact",
    summary="Contact Blood Donor",
    description="Dispatches automated Twilio notification alert to the selected donor.",
)
def contact_donor(
    donor_id: str,
    body: DonorContactRequest,
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.DOCTOR, UserRole.HOSPITAL_STAFF, UserRole.ADMIN
    ])),
    db: Session = Depends(get_db),
):
    return donor_service.contact_donor(db, donor_id, body.emergencyId, current_user)


@router.post(
    "/donors/{donor_id}/response",
    summary="Record Donor SOS Response",
    description="Records whether the contacted donor accepted or declined the emergency request.",
)
def record_response(
    donor_id: str,
    body: DonorResponseRequest,
    current_user: Optional[UserProfileSchema] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    return donor_service.record_donor_response(
        db, donor_id, body.status, share_location=body.shareLocation or False, current_user=current_user
    )
