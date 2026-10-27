from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.hospital import Hospital
from app.models.blood_inventory import BloodInventory
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
            district=h.district,
            pincode=h.pincode,
            coordinates=Coordinates(lat=h.lat, lng=h.lng) if (h.lat is not None and h.lng is not None) else None,
            type=h.type,
            category=h.category or "hospital",
            services=h.services,
            bloodBankAvailable=h.blood_bank_available,
            organTransplantCenter=h.organ_transplant_center,
            emergencyBays=h.emergency_bays or 0,
            contactNumber=h.contact_number,
            isCurrentHospital=h.is_current_hospital,
        )

    @staticmethod
    def get_all(
        db: Session,
        city: Optional[str] = None,
        district: Optional[str] = None,
        category: Optional[str] = None,
        type: Optional[str] = None,
        blood_bank_available: Optional[bool] = None,
        organ_transplant_center: Optional[bool] = None,
    ) -> List[HospitalResponse]:
        query = db.query(Hospital)
        if city:
            query = query.filter(Hospital.city.ilike(f"%{city.strip()}%"))
        if district:
            query = query.filter(Hospital.district.ilike(f"%{district.strip()}%"))
        if category:
            query = query.filter(Hospital.category.ilike(f"%{category.strip()}%"))
        if type:
            query = query.filter(Hospital.type.ilike(f"%{type.strip()}%"))
        if blood_bank_available is not None:
            query = query.filter(Hospital.blood_bank_available == blood_bank_available)
        if organ_transplant_center is not None:
            query = query.filter(Hospital.organ_transplant_center == organ_transplant_center)
        hospitals = query.all()
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

        # Standard blood groups default to 0 units unless verified records exist in DB
        blood_inventory = {
            "A+": 0, "A-": 0, "B+": 0, "B-": 0,
            "AB+": 0, "AB-": 0, "O+": 0, "O-": 0,
        }
        db_inventories = db.query(BloodInventory).filter(BloodInventory.hospital_id == hospital_id).all()
        for item in db_inventories:
            bg = item.blood_group.upper().strip()
            blood_inventory[bg] = blood_inventory.get(bg, 0) + (item.units_available or 0)

        total_bays = h.emergency_bays or 0
        return HospitalInventoryResponse(
            hospitalId=h.id,
            hospitalName=h.name,
            bloodInventory=blood_inventory,
            organAvailableCount=1 if h.organ_transplant_center else 0,
            emergencyBaysTotal=total_bays,
            emergencyBaysAvailable=max(0, total_bays - 5) if total_bays >= 5 else total_bays,
        )


hospital_service = HospitalService()

