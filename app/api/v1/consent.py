from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.consent import ConsentResponse, ConsentUpdateRequest
from app.schemas.auth import UserProfileSchema
from app.services.consent_service import consent_service
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/consent", tags=["Consent Management"])


@router.get(
    "",
    response_model=ConsentResponse,
    summary="Get Current User Consent",
    description="Retrieves active privacy and data sharing consent preferences for the authenticated user.",
)
def get_my_consent(
    current_user: UserProfileSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return consent_service.get_user_consent(db, current_user.id)


@router.patch(
    "",
    response_model=ConsentResponse,
    summary="Update User Consent",
    description="Updates granular consent preferences (Live GPS, Communication, Donation requests, Health data).",
)
def update_my_consent(
    data: ConsentUpdateRequest,
    current_user: UserProfileSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return consent_service.update_user_consent(db, current_user.id, data, current_user)
