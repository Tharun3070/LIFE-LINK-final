from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class BloodEmergencyRequest(BaseModel):
    bloodGroup: str = Field(..., description="Blood group e.g. O-, A+, etc.")
    unitsRequired: int = Field(..., ge=1, le=20)
    priority: str = Field("critical", description="critical, high, medium, low")
    hospitalId: str
    notes: Optional[str] = None
    locationLat: Optional[float] = Field(None, alias="location_lat", description="Patient emergency origin latitude")
    locationLng: Optional[float] = Field(None, alias="location_lng", description="Patient emergency origin longitude")


class EmergencyCreate(BaseModel):
    type: str = Field(..., description="blood, organ, ambulance, multi")
    priority: str = Field("critical", description="critical, high, medium, low")
    status: Optional[str] = Field(None, description="created, searching, coordinating, etc.")
    hospitalId: Optional[str] = None
    hospitalName: Optional[str] = None
    patientId: Optional[str] = Field(None, description="Linked patient user ID")
    description: str
    bloodGroup: Optional[str] = None
    unitsRequired: Optional[int] = None
    organType: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    locationLat: Optional[float] = Field(None, alias="location_lat", description="Emergency origin latitude")
    locationLng: Optional[float] = Field(None, alias="location_lng", description="Emergency origin longitude")


class EmergencyUpdate(BaseModel):
    priority: Optional[str] = None
    status: Optional[str] = None
    patientId: Optional[str] = None
    eta: Optional[int] = None
    description: Optional[str] = None
    locationLat: Optional[float] = Field(None, alias="location_lat")
    locationLng: Optional[float] = Field(None, alias="location_lng")


class EmergencyResponse(BaseModel):
    id: str
    patientId: Optional[str] = None
    type: str
    priority: str
    status: str
    hospitalId: str
    hospitalName: str
    createdAt: str
    updatedAt: str
    description: str
    eta: Optional[int] = None
    assignedResourceIds: Optional[List[str]] = None
    resolvedAt: Optional[str] = None
    bloodGroup: Optional[str] = None
    unitsRequired: Optional[int] = None
    organType: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    locationLat: Optional[float] = None
    locationLng: Optional[float] = None


class EmergencyEventResponse(BaseModel):
    id: str
    emergencyId: str
    timestamp: str
    actor: str
    action: str
    resource: Optional[str] = None
    authorization: Optional[str] = None
    status: str = "success"
    metadata: Optional[Dict[str, Any]] = None


class KPIDataResponse(BaseModel):
    activeEmergencies: int
    bloodRequests: int
    organAlerts: int
    ambulancesActive: int
    avgResponseTimeSeconds: int
    donorAcceptanceRate: int
