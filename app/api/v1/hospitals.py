from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.hospital import HospitalResponse, HospitalInventoryResponse
from app.schemas.emergency import EmergencyResponse
from app.services.hospital_service import hospital_service
from app.services.emergency_service import emergency_service

router = APIRouter(prefix="/hospitals", tags=["Hospitals"])


@router.get(
    "",
    response_model=List[HospitalResponse],
    summary="List Partner Hospitals",
    description="Returns the hospital directory in the LifeLink network.",
)
def list_hospitals(db: Session = Depends(get_db)):
    return hospital_service.get_all(db)


@router.get(
    "/{hospital_id}",
    response_model=HospitalResponse,
    summary="Get Hospital Details",
    description="Retrieves address, trauma bays, blood bank, and transplant center capabilities.",
)
def get_hospital(hospital_id: str, db: Session = Depends(get_db)):
    return hospital_service.get_by_id(db, hospital_id)


@router.get(
    "/{hospital_id}/inventory",
    response_model=HospitalInventoryResponse,
    summary="Get Hospital Resource Inventory",
    description="Returns available blood units and emergency bay capacity.",
)
def get_hospital_inventory(hospital_id: str, db: Session = Depends(get_db)):
    return hospital_service.get_inventory(db, hospital_id)


@router.get(
    "/{hospital_id}/emergencies",
    response_model=List[EmergencyResponse],
    summary="Get Hospital Emergencies",
    description="Returns active emergencies coordinated by the specified hospital.",
)
def get_hospital_emergencies(hospital_id: str, db: Session = Depends(get_db)):
    all_emergencies = emergency_service.get_all(db)
    return [e for e in all_emergencies if e.hospitalId == hospital_id]
