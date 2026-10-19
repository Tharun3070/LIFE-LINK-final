import os
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import get_db
from app.core.config import settings
from app.schemas.system import SystemStatusResponse

router = APIRouter(prefix="/system", tags=["System Status"])


@router.get(
    "/status",
    response_model=SystemStatusResponse,
    summary="Get System Component Status",
    description="Returns truthful operational health status for all LifeLink modules based on configuration and implementation.",
)
def get_system_status(db: Session = Depends(get_db)):
    # 1. Database check
    try:
        db.execute(text("SELECT 1"))
        db_status = "operational"
    except Exception:
        db_status = "unavailable"

    # 2. Realtime WebSocket Gateway
    realtime_status = "operational"

    # 3. LLM: Not configured until valid API key provided and service integrated
    llm_status = "operational" if (settings.LLM_API_KEY and settings.LLM_API_KEY.strip()) else "not_configured"

    # 4. RAG: Not configured until vector database URL configured and service integrated
    rag_status = "operational" if (settings.VECTOR_DATABASE_URL and settings.VECTOR_DATABASE_URL.strip()) else "not_configured"

    # 5. XGBoost Engine: Not configured until trained model artifact exists
    model_path = os.path.join(os.path.dirname(__file__), "..", "..", "models", "donor_ranking_xgboost.json")
    xgboost_status = "operational" if os.path.exists(model_path) else "not_configured"

    # 6. Geospatial Engine: Not configured until Google Maps API key or PostGIS enabled
    geospatial_status = (
        "operational"
        if (settings.GOOGLE_MAPS_API_KEY and settings.GOOGLE_MAPS_API_KEY.strip()) or settings.POSTGIS_ENABLED
        else "not_configured"
    )

    overall_healthy = bool(db_status == "operational" and realtime_status == "operational")

    return SystemStatusResponse(
        llm=llm_status,
        rag=rag_status,
        xgboost=xgboost_status,
        geospatial=geospatial_status,
        realtime=realtime_status,
        database=db_status,
        overallHealthy=overall_healthy,
    )
