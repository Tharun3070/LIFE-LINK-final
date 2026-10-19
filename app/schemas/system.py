from typing import Dict, Any, Optional
from pydantic import BaseModel


class SystemStatusResponse(BaseModel):
    llm: str = "operational"
    rag: str = "operational"
    xgboost: str = "operational"
    geospatial: str = "operational"
    realtime: str = "operational"
    database: str = "operational"
    overallHealthy: bool = True


class HealthCheckResponse(BaseModel):
    status: str = "ok"
    service: str = "lifelink-backend"
    version: str = "1.0.0"
    environment: str = "development"
    database: Optional[str] = "connected"
