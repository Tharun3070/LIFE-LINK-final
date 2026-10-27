from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.schemas.hospital import BloodBankResponse, BloodBankInventoryResponse
from app.schemas.donor import Coordinates


class BloodBankService:
    @staticmethod
    def _map_blood_bank_to_response(bb: BloodBank) -> BloodBankResponse:
        coords = None
        if bb.lat is not None and bb.lng is not None:
            coords = Coordinates(lat=bb.lat, lng=bb.lng)
        return BloodBankResponse(
            id=bb.id,
            name=bb.name,
            address=bb.address,
            city=bb.city,
            district=bb.district,
            pincode=bb.pincode,
            coordinates=coords,
            contactNumber=bb.contact_number,
            services=bb.services,
            hospitalId=bb.hospital_id,
            dataProvenance=bb.data_provenance or "production",
        )

    @staticmethod
    def get_all(
        db: Session,
        city: Optional[str] = None,
        district: Optional[str] = None,
        hospital_id: Optional[str] = None,
    ) -> List[BloodBankResponse]:
        query = db.query(BloodBank)
        if city:
            query = query.filter(BloodBank.city.ilike(f"%{city.strip()}%"))
        if district:
            query = query.filter(BloodBank.district.ilike(f"%{district.strip()}%"))
        if hospital_id:
            query = query.filter(BloodBank.hospital_id == hospital_id.strip())
        blood_banks = query.all()
        return [BloodBankService._map_blood_bank_to_response(bb) for bb in blood_banks]

    @staticmethod
    def get_by_id(db: Session, blood_bank_id: str) -> BloodBankResponse:
        bb = db.query(BloodBank).filter(BloodBank.id == blood_bank_id).first()
        if not bb:
            raise HTTPException(status_code=404, detail="Blood bank not found")
        return BloodBankService._map_blood_bank_to_response(bb)

    @staticmethod
    def get_inventory(db: Session, blood_bank_id: str) -> BloodBankInventoryResponse:
        bb = db.query(BloodBank).filter(BloodBank.id == blood_bank_id).first()
        if not bb:
            raise HTTPException(status_code=404, detail="Blood bank not found")

        blood_inventory = {
            "A+": 0, "A-": 0, "B+": 0, "B-": 0,
            "AB+": 0, "AB-": 0, "O+": 0, "O-": 0,
        }
        inventories = db.query(BloodInventory).filter(BloodInventory.blood_bank_id == blood_bank_id).all()
        total_units = 0
        for item in inventories:
            bg = item.blood_group.upper().strip()
            units = item.units_available or 0
            blood_inventory[bg] = blood_inventory.get(bg, 0) + units
            total_units += units

        return BloodBankInventoryResponse(
            bloodBankId=bb.id,
            bloodBankName=bb.name,
            bloodInventory=blood_inventory,
            totalUnitsAvailable=total_units,
        )


blood_bank_service = BloodBankService()
