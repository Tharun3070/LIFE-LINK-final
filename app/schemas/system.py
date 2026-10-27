from typing import Dict, Any, Optional
from pydantic import BaseModel


class SystemStatusResponse(BaseModel):
    llm: str = "operational"
    rag: str = "operational"
    xgboost: str = "operational"
    geospatial: str = "operational"
    realtime: str = "operational"
    database: str = "operational"
    notifications: str = "mock_isolated"
    deterministic_fallback: str = "operational"
    overallHealthy: bool = True
    rag_details: Optional[Dict[str, Any]] = None
    llm_details: Optional[Dict[str, Any]] = None



class HealthCheckResponse(BaseModel):
    status: str = "ok"
    service: str = "lifelink-backend"
    version: str = "1.0.0"
    environment: str = "development"
    database: Optional[str] = "connected"
