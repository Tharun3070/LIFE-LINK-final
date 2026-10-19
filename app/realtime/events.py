from enum import Enum
from typing import Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class RealtimeEventType(str, Enum):
    EMERGENCY_CREATED = "emergency.created"
    EMERGENCY_UPDATED = "emergency.updated"
    DONOR_CONTACTED = "donor.contacted"
    DONOR_ACCEPTED = "donor.accepted"
    DONOR_DECLINED = "donor.declined"
    DONOR_LOCATION_UPDATED = "donor.location_updated"
    ORGAN_AVAILABLE = "organ.available"
    ORGAN_VIABILITY_UPDATED = "organ.viability_updated"
    AMBULANCE_LOCATION_UPDATED = "ambulance.location_updated"
    AMBULANCE_STATUS_UPDATED = "ambulance.status_updated"
    AMBULANCE_ETA_UPDATED = "ambulance.eta_updated"
    ROUTE_UPDATED = "route.updated"
    SYSTEM_STATUS_UPDATED = "system.status_updated"
    CONNECTION_ESTABLISHED = "connection.established"
    CONNECTION_LOST = "connection.lost"


class RealtimeEvent(BaseModel):
    type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
