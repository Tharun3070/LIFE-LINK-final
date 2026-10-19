from typing import Optional, Dict
from pydantic import BaseModel
from app.schemas.donor import Coordinates


class HospitalResponse(BaseModel):
    id: str
    name: str
    address: str
    city: str
    coordinates: Coordinates
    type: str # general, specialty, trauma, teaching
    bloodBankAvailable: bool
    organTransplantCenter: bool
    emergencyBays: int
    contactNumber: Optional[str] = None
    isCurrentHospital: Optional[bool] = False


class HospitalInventoryResponse(BaseModel):
    hospitalId: str
    hospitalName: str
    bloodInventory: Dict[str, int] # e.g. {"O+": 12, "O-": 0, "A+": 8}
    organAvailableCount: int
    emergencyBaysTotal: int
    emergencyBaysAvailable: int
