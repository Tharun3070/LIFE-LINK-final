from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.ambulance import (
    AmbulanceResponse,
    RouteOptionSchema,
    AmbulanceLocationUpdate,
    AmbulanceStatusUpdate,
    AmbulanceTelemetryIngest,
    AmbulanceTelemetryIngestResponse,
)
from app.schemas.auth import UserProfileSchema
from app.services.ambulance_service import ambulance_service
from app.core.dependencies import get_current_user, require_role
from app.core.permissions import UserRole

router = APIRouter(prefix="/ambulances", tags=["Ambulance Intelligence"])


@router.get(
    "",
    response_model=List[AmbulanceResponse],
    summary="List Ambulances",
    description="Returns active ambulances across hospital emergency networks.",
)
def list_ambulances(db: Session = Depends(get_db)):
    return ambulance_service.get_all(db)


@router.post(
    "/telemetry/ingest",
    response_model=AmbulanceTelemetryIngestResponse,
    summary="Ingest Live GPS Telemetry",
    description="Secure device and mobile app telemetry ingestion endpoint for real-time GPS coordinates.",
)
def ingest_telemetry(
    data: AmbulanceTelemetryIngest,
    current_user: UserProfileSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ambulance_service.ingest_telemetry(db, data, current_user)


@router.get(
    "/{ambulance_id}",
    response_model=AmbulanceResponse,
    summary="Get Ambulance Details",
    description="Retrieves live telemetry, assigned route, and destination for a specific ambulance unit.",
)
def get_ambulance(ambulance_id: str, db: Session = Depends(get_db)):
    return ambulance_service.get_by_id(db, ambulance_id)


@router.get(
    "/{ambulance_id}/routes",
    response_model=List[RouteOptionSchema],
    summary="Get Multi-Route Comparison",
    description="Returns Route A, Route B, Route C comparison with traffic condition, feasibility, and AI recommendation.",
)
def get_routes(ambulance_id: str, db: Session = Depends(get_db)):
    return ambulance_service.get_routes(db, ambulance_id)


@router.get(
    "/{ambulance_id}/location",
    summary="Get Ambulance GPS Location",
    description="Returns current coordinates, heading, and speed.",
)
def get_location(ambulance_id: str, db: Session = Depends(get_db)):
    amb = ambulance_service.get_by_id(db, ambulance_id)
    return {
        "ambulanceId": ambulance_id,
        "currentLocation": amb.currentLocation,
        "speedKmh": amb.speedKmh,
        "updatedAt": amb.updatedAt,
    }


@router.get(
    "/{ambulance_id}/eta",
    summary="Get Ambulance ETA",
    description="Returns estimated arrival minutes to designated hospital trauma bay.",
)
def get_eta(ambulance_id: str, db: Session = Depends(get_db)):
    amb = ambulance_service.get_by_id(db, ambulance_id)
    return {
        "ambulanceId": ambulance_id,
        "etaMinutes": amb.etaMinutes,
        "destination": amb.destination,
        "updatedAt": amb.updatedAt,
    }


@router.post(
    "/{ambulance_id}/location",
    response_model=AmbulanceResponse,
    summary="Update Ambulance Location",
    description="Telemetry ingestion endpoint for GPS tracking updates.",
)
def update_location(
    ambulance_id: str,
    data: AmbulanceLocationUpdate,
    current_user: UserProfileSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ambulance_service.update_location(db, ambulance_id, data, current_user)


@router.post(
    "/{ambulance_id}/status",
    response_model=AmbulanceResponse,
    summary="Update Ambulance Dispatch Status",
    description="Updates dispatch state (idle, dispatched, en_route, at_hospital).",
)
def update_status(
    ambulance_id: str,
    data: AmbulanceStatusUpdate,
    current_user: UserProfileSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ambulance_service.update_status(db, ambulance_id, data, current_user)
