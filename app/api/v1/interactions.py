from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.permissions import UserRole
from app.schemas.auth import UserProfileSchema
from app.schemas.interaction import (
    CandidateSelectionRequest,
    ContactAttemptRequest,
    ContactDeliveredRequest,
    ContactFailedRequest,
    ContactTimeoutRequest,
    InteractionCancellationRequest,
    DonorResponseRecordRequest,
    DonationCompletionRequest,
    DonorInteractionResponse,
    InteractionListResponse,
)
from app.services.interaction_service import interaction_service

router = APIRouter(prefix="/blood/interactions", tags=["Blood Emergency Interactions"])


@router.post(
    "/candidate",
    response_model=DonorInteractionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record Candidate Selection (Snapshot)",
    description="Logs candidate donor selection for an emergency with immutable dispatch-time features.",
)
def record_candidate(
    req: CandidateSelectionRequest,
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.DOCTOR, UserRole.HOSPITAL_STAFF, UserRole.ADMIN
    ])),
    db: Session = Depends(get_db),
):
    return interaction_service.record_candidate_selection(db, req, current_user)


@router.post(
    "/{interaction_id}/attempt",
    response_model=DonorInteractionResponse,
    summary="Record Contact Attempt",
    description="Logs contact dispatch to a candidate donor (verifies emergency communication consent).",
)
def record_contact_attempt(
    interaction_id: str,
    req: ContactAttemptRequest,
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.DOCTOR, UserRole.HOSPITAL_STAFF, UserRole.ADMIN
    ])),
    db: Session = Depends(get_db),
):
    return interaction_service.record_contact_attempt(db, interaction_id, req, current_user)


@router.post(
    "/{interaction_id}/delivered",
    response_model=DonorInteractionResponse,
    summary="Record Contact Delivery Confirmation",
    description="Logs provider carrier or push delivery confirmation for an attempted contact.",
)
def record_delivery(
    interaction_id: str,
    req: ContactDeliveredRequest,
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.DOCTOR, UserRole.HOSPITAL_STAFF, UserRole.ADMIN
    ])),
    db: Session = Depends(get_db),
):
    return interaction_service.record_contact_delivery(db, interaction_id, req, current_user)


@router.post(
    "/{interaction_id}/response",
    response_model=DonorInteractionResponse,
    summary="Record Verified Donor Response",
    description="Logs donor acceptance or decline with response latency calculation. Donors can only respond to their own requests.",
)
def record_response(
    interaction_id: str,
    req: DonorResponseRecordRequest,
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.DOCTOR, UserRole.HOSPITAL_STAFF, UserRole.DONOR, UserRole.ADMIN
    ])),
    db: Session = Depends(get_db),
):
    return interaction_service.record_donor_response(db, interaction_id, req, current_user)


@router.post(
    "/{interaction_id}/complete",
    response_model=DonorInteractionResponse,
    summary="Record Verified Donation Completion",
    description="Logs verified clinical donation completion at the receiving hospital or blood bank.",
)
def record_completion(
    interaction_id: str,
    req: DonationCompletionRequest,
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.DOCTOR, UserRole.HOSPITAL_STAFF, UserRole.ADMIN
    ])),
    db: Session = Depends(get_db),
):
    return interaction_service.record_donation_completion(db, interaction_id, req, current_user)


@router.post(
    "/{interaction_id}/failed",
    response_model=DonorInteractionResponse,
    summary="Record Contact Failure",
    description="Logs contact transmission or carrier failure for a dispatch attempt.",
)
def record_contact_failed(
    interaction_id: str,
    req: ContactFailedRequest,
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.DOCTOR, UserRole.HOSPITAL_STAFF, UserRole.ADMIN
    ])),
    db: Session = Depends(get_db),
):
    return interaction_service.record_contact_failed(db, interaction_id, req, current_user)


@router.post(
    "/{interaction_id}/timeout",
    response_model=DonorInteractionResponse,
    summary="Record Response Timeout",
    description="Logs elapsed donor response timeout window, marking candidate unreachable without fabricating response latency.",
)
def record_contact_timeout(
    interaction_id: str,
    req: ContactTimeoutRequest,
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.DOCTOR, UserRole.HOSPITAL_STAFF, UserRole.ADMIN
    ])),
    db: Session = Depends(get_db),
):
    return interaction_service.record_contact_timeout(db, interaction_id, req, current_user)


@router.post(
    "/{interaction_id}/cancel",
    response_model=DonorInteractionResponse,
    summary="Record Interaction Cancellation",
    description="Logs cancellation of a pending or accepted candidate interaction when emergency needs resolve or change.",
)
def record_interaction_cancellation(
    interaction_id: str,
    req: InteractionCancellationRequest,
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.DOCTOR, UserRole.HOSPITAL_STAFF, UserRole.ADMIN
    ])),
    db: Session = Depends(get_db),
):
    return interaction_service.record_interaction_cancellation(db, interaction_id, req, current_user)


@router.get(
    "/{interaction_id}",
    response_model=DonorInteractionResponse,
    summary="Get Interaction Details",
    description="Retrieves a specific interaction. Donors are strictly restricted to their own records.",
)
def get_interaction(
    interaction_id: str,
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.DOCTOR, UserRole.HOSPITAL_STAFF, UserRole.DONOR, UserRole.ADMIN
    ])),
    db: Session = Depends(get_db),
):
    return interaction_service.get_interaction_by_id(db, interaction_id, current_user)


@router.get(
    "",
    response_model=InteractionListResponse,
    summary="List Interaction History",
    description="Queries interaction records. Enforces privacy boundaries so donors cannot inspect other donors.",
)
def list_interactions(
    emergencyId: Optional[str] = Query(None, description="Filter by emergency ID"),
    donorId: Optional[str] = Query(None, description="Filter by donor ID (privileged roles only)"),
    isSynthetic: Optional[bool] = Query(None, description="Filter by synthetic flag"),
    dataProvenance: Optional[str] = Query(None, description="Filter by provenance (production, synthetic_simulation, test_fixture)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.DOCTOR, UserRole.HOSPITAL_STAFF, UserRole.DONOR, UserRole.ADMIN
    ])),
    db: Session = Depends(get_db),
):
    items, total = interaction_service.get_interaction_history(
        db=db,
        current_user=current_user,
        emergency_id=emergencyId,
        donor_id=donorId,
        is_synthetic=isSynthetic,
        data_provenance=dataProvenance,
        limit=limit,
        offset=offset,
    )
    return InteractionListResponse(items=items, total=total, limit=limit, offset=offset)
