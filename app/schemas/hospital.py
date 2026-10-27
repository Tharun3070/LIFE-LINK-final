from typing import Optional, Dict
from pydantic import BaseModel
from app.schemas.donor import Coordinates


class HospitalResponse(BaseModel):
    id: str
    name: str
    address: str
    city: str
    district: Optional[str] = None
    pincode: Optional[str] = None
    coordinates: Optional[Coordinates] = None
    type: str  # general, specialty, trauma, teaching
    category: Optional[str] = "hospital"
    services: Optional[str] = None
    bloodBankAvailable: bool
    organTransplantCenter: bool
    emergencyBays: int
    contactNumber: Optional[str] = None
    isCurrentHospital: Optional[bool] = False


class BloodBankResponse(BaseModel):
    id: str
    name: str
    address: str
    city: str
    district: Optional[str] = None
    pincode: Optional[str] = None
    coordinates: Optional[Coordinates] = None
    contactNumber: Optional[str] = None
    services: Optional[str] = None
    hospitalId: Optional[str] = None
    dataProvenance: Optional[str] = "production"


class HospitalInventoryResponse(BaseModel):
    hospitalId: str
    hospitalName: str
    bloodInventory: Dict[str, int]  # e.g. {"O+": 12, "O-": 0, "A+": 8}
    organAvailableCount: int
    emergencyBaysTotal: int
    emergencyBaysAvailable: int


class BloodBankInventoryResponse(BaseModel):
    bloodBankId: str
    bloodBankName: str
    bloodInventory: Dict[str, int]
    totalUnitsAvailable: int


