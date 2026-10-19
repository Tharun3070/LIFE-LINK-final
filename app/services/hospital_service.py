from typing import List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.hospital import Hospital
from app.schemas.hospital import HospitalResponse, HospitalInventoryResponse
from app.schemas.donor import Coordinates


class HospitalService:
    @staticmethod
    def _map_hospital_to_response(h: Hospital) -> HospitalResponse:
        return HospitalResponse(
            id=h.id,
            name=h.name,
            address=h.address,
            city=h.city,
            coordinates=Coordinates(lat=h.lat, lng=h.lng),
            type=h.type,
            bloodBankAvailable=h.blood_bank_available,
            organTransplantCenter=h.organ_transplant_center,
            emergencyBays=h.emergency_bays,
            contactNumber=h.contact_number,
            isCurrentHospital=h.is_current_hospital,
        )

    @staticmethod
    def get_all(db: Session) -> List[HospitalResponse]:
        hospitals = db.query(Hospital).all()
        return [HospitalService._map_hospital_to_response(h) for h in hospitals]

    @staticmethod
    def get_by_id(db: Session, hospital_id: str) -> HospitalResponse:
        h = db.query(Hospital).filter(Hospital.id == hospital_id).first()
        if not h:
            raise HTTPException(status_code=404, detail="Hospital not found")
        return HospitalService._map_hospital_to_response(h)

    @staticmethod
    def get_inventory(db: Session, hospital_id: str) -> HospitalInventoryResponse:
        h = db.query(Hospital).filter(Hospital.id == hospital_id).first()
        if not h:
            raise HTTPException(status_code=404, detail="Hospital not found")

        # Standard simulated inventory levels for development / hospital operations
        return HospitalInventoryResponse(
            hospitalId=h.id,
            hospitalName=h.name,
            bloodInventory={
                "A+": 14, "A-": 4, "B+": 18, "B-": 2,
                "AB+": 6, "AB-": 1, "O+": 22, "O-": 0,
            },
            organAvailableCount=1 if h.organ_transplant_center else 0,
            emergencyBaysTotal=h.emergency_bays,
            emergencyBaysAvailable=max(2, h.emergency_bays - 5),
        )


hospital_service = HospitalService()
