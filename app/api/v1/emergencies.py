from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.emergency import (
    EmergencyCreate,
    EmergencyUpdate,
    EmergencyResponse,
    EmergencyEventResponse,
    KPIDataResponse,
)
from app.schemas.auth import UserProfileSchema
from app.services.emergency_service import emergency_service
from app.core.dependencies import get_current_user, require_role, get_optional_current_user
from app.core.permissions import UserRole

router = APIRouter(tags=["Emergencies"])


@router.get(
    "/emergencies",
    response_model=List[EmergencyResponse],
    summary="List Emergencies",
    description="Returns all registered emergencies in the LifeLink network.",
)
def list_emergencies(
    current_user: Optional[UserProfileSchema] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    return emergency_service.get_all(db, current_user)


@router.get(
    "/emergencies/patient/me",
    response_model=Optional[EmergencyResponse],
    summary="Get Current Patient Emergency",
    description="Retrieves the active emergency securely linked to the authenticated patient.",
)
def get_my_patient_emergency(
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.PATIENT, UserRole.ADMIN
    ])),
    db: Session = Depends(get_db),
):
    return emergency_service.get_patient_emergency(db, current_user)


@router.post(
    "/emergencies",
    response_model=EmergencyResponse,
    summary="Create Emergency SOS",
    description="Registers a new emergency in the coordination center (Blood, Organ, Ambulance).",
)
def create_emergency(
    data: EmergencyCreate,
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.DOCTOR, UserRole.HOSPITAL_STAFF, UserRole.ADMIN
    ])),
    db: Session = Depends(get_db),
):
    return emergency_service.create(db, data, current_user)


@router.get(
    "/emergencies/{emergency_id}",
    response_model=EmergencyResponse,
    summary="Get Emergency Details",
    description="Retrieves status and metadata for a specific emergency.",
)
def get_emergency(
    emergency_id: str,
    current_user: Optional[UserProfileSchema] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    return emergency_service.get_by_id(db, emergency_id, current_user)


@router.patch(
    "/emergencies/{emergency_id}",
    response_model=EmergencyResponse,
    summary="Update Emergency",
    description="Updates emergency priority, status, or ETA.",
)
def update_emergency(
    emergency_id: str,
    data: EmergencyUpdate,
    current_user: UserProfileSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return emergency_service.update(db, emergency_id, data, current_user)


@router.post(
    "/emergencies/{emergency_id}/resolve",
    response_model=EmergencyResponse,
    summary="Resolve Emergency",
    description="Marks an active emergency as successfully resolved.",
)
def resolve_emergency(
    emergency_id: str,
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.DOCTOR, UserRole.HOSPITAL_STAFF, UserRole.ADMIN, UserRole.TRANSPLANT_COORDINATOR, UserRole.AMBULANCE_OPERATOR
    ])),
    db: Session = Depends(get_db),
):
    return emergency_service.resolve(db, emergency_id, current_user)


@router.post(
    "/emergencies/{emergency_id}/cancel",
    response_model=EmergencyResponse,
    summary="Cancel Emergency",
    description="Cancels an emergency response coordination.",
)
def cancel_emergency(
    emergency_id: str,
    current_user: UserProfileSchema = Depends(require_role([
        UserRole.DOCTOR, UserRole.HOSPITAL_STAFF, UserRole.ADMIN, UserRole.TRANSPLANT_COORDINATOR, UserRole.AMBULANCE_OPERATOR
    ])),
    db: Session = Depends(get_db),
):
    return emergency_service.cancel(db, emergency_id, current_user)


# ---- Dashboard KPIs & Activity (compatible with frontend apiClient) ----

@router.get(
    "/dashboard/kpis",
    response_model=KPIDataResponse,
    summary="Get Command Center KPIs",
    description="Returns real-time aggregated metrics across all emergency response modules.",
)
def get_dashboard_kpis(db: Session = Depends(get_db)):
    return emergency_service.get_kpis(db)


@router.get(
    "/activity",
    response_model=List[EmergencyEventResponse],
    summary="Get Activity Timeline",
    description="Returns real-time orchestration events and actions.",
)
def get_activity_timeline(
    emergencyId: Optional[str] = Query(None, description="Filter timeline by emergency ID"),
    db: Session = Depends(get_db),
):
    return emergency_service.get_timeline(db, emergencyId)
