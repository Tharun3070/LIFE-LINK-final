from typing import Optional
from pydantic import BaseModel


class ConsentResponse(BaseModel):
    id: str
    userId: str
    liveLocation: bool
    emergencyCommunication: bool
    donationRequests: bool
    healthDataSharing: bool
    updatedAt: str


class ConsentUpdateRequest(BaseModel):
    liveLocation: Optional[bool] = None
    emergencyCommunication: Optional[bool] = None
    donationRequests: Optional[bool] = None
    healthDataSharing: Optional[bool] = None
