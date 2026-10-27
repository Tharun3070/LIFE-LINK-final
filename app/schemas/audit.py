from typing import Optional, Dict, Any
from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: str
    timestamp: str
    actor: str
    actorType: str # user, system, ai, donor
    action: str
    resource: str
    resourceId: Optional[str] = None
    authorization: Optional[str] = None
    status: str = "success" # success, failed, pending
    module: str # blood, organ, ambulance, system, auth
    ipAddress: Optional[str] = None
    sessionId: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    previousHash: Optional[str] = None
    recordHash: Optional[str] = None


class AuditLogCreate(BaseModel):
    actor: str
    actorType: str = "user"
    action: str
    resource: str
    resourceId: Optional[str] = None
    authorization: Optional[str] = None
    status: str = "success"
    module: str
    ipAddress: Optional[str] = None
    sessionId: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
