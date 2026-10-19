from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.organ import OrganResponse, ClinicalReviewRequest, OrganRequest, OrganRequestResponse
from app.schemas.auth import UserProfileSchema
from app.services.organ_service import organ_service
from app.core.dependencies import get_current_user, require_role
from app.core.permissions import UserRole

router = APIRouter(prefix="/organs", tags=["Organ Intelligence"])


@router.get(
    "",
    response_model=List[OrganResponse],
    summary="List Available Organs",
    description="Returns all registered organs with real-time viability countdown and AI reachability scores.",
)
@router.get(
    "/available",
    response_model=List[OrganResponse],
    summary="List Available Organs (Frontend Alias)",
    description="Frontend compatibility endpoint returning available organs.",
)
def list_organs(db: Session = Depends(get_db)):
    return organ_service.get_all(db)


@router.get(
    "/{organ_id}",
    response_model=OrganResponse,
    summary="Get Organ Intelligence Details",
    description="Returns viability status, donor source hospital, and AI recommendation rationale.",
)
def get_organ(organ_id: str, db: Session = Depends(get_db)):
    return organ_service.get_by_id(db, organ_id)


@router.post(
    "/{organ_id}/clinical-review",
    response_model=OrganResponse,
    summary="Submit Clinical Review Decision",
    description="Mandatory human-in-the-loop clinical review for organ allocation (Doctor / Transplant Coordinator).",
)
def request_clinical_review(
    organ_id: str,
    body: ClinicalReviewRequest = ClinicalReviewRequest(),
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.DOCTOR, UserRole.TRANSPLANT_COORDINATOR, UserRole.ADMIN
    ])),
    db: Session = Depends(get_db),
):
    return organ_service.request_clinical_review(db, organ_id, current_user, review_data=body)


@router.post(
    "/requests",
    response_model=OrganRequestResponse,
    summary="Create Organ Alert Search",
    description="Initiates an urgent organ match search across transplant partner hospitals, persisting an emergency record, timeline entry, and audit trail.",
)
def create_organ_request(
    req: OrganRequest,
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.DOCTOR, UserRole.TRANSPLANT_COORDINATOR, UserRole.ADMIN
    ])),
    db: Session = Depends(get_db),
):
    return organ_service.create_organ_request(db, req, current_user)
