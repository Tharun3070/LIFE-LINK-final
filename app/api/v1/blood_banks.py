from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.hospital import BloodBankResponse, BloodBankInventoryResponse
from app.services.blood_bank_service import blood_bank_service

router = APIRouter(prefix="/blood-banks", tags=["Blood Banks"])


@router.get(
    "",
    response_model=List[BloodBankResponse],
    summary="List Blood Banks",
    description="Returns the blood banks directory with optional filtering by city, district, or affiliated hospital.",
)
def list_blood_banks(
    city: Optional[str] = None,
    district: Optional[str] = None,
    hospital_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return blood_bank_service.get_all(
        db=db,
        city=city,
        district=district,
        hospital_id=hospital_id,
    )


@router.get(
    "/{blood_bank_id}",
    response_model=BloodBankResponse,
    summary="Get Blood Bank Details",
    description="Retrieves specific blood bank metadata, address, contact info, and coordinates.",
)
def get_blood_bank(blood_bank_id: str, db: Session = Depends(get_db)):
    return blood_bank_service.get_by_id(db, blood_bank_id)


@router.get(
    "/{blood_bank_id}/inventory",
    response_model=BloodBankInventoryResponse,
    summary="Get Blood Bank Inventory",
    description="Returns verified blood units available by ABO/Rh group for the specified blood bank.",
)
def get_blood_bank_inventory(blood_bank_id: str, db: Session = Depends(get_db)):
    return blood_bank_service.get_inventory(db, blood_bank_id)
