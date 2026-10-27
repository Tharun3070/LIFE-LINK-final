from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.emergencies import router as emergencies_router
from app.api.v1.blood import router as blood_router
from app.api.v1.donors import router as donors_router
from app.api.v1.organs import router as organs_router
from app.api.v1.ambulances import router as ambulances_router
from app.api.v1.hospitals import router as hospitals_router
from app.api.v1.audit import router as audit_router
from app.api.v1.consent import router as consent_router
from app.api.v1.system import router as system_router
from app.api.v1.realtime import router as realtime_router
from app.api.v1.interactions import router as interactions_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.clinical_guidance import router as clinical_guidance_router
from app.api.v1.blood_banks import router as blood_banks_router

# Canonical Versioned API Router (/api/v1/...)
api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(emergencies_router)
api_v1_router.include_router(blood_router)
api_v1_router.include_router(donors_router)
api_v1_router.include_router(organs_router)
api_v1_router.include_router(ambulances_router)
api_v1_router.include_router(hospitals_router)
api_v1_router.include_router(blood_banks_router)
api_v1_router.include_router(audit_router)
api_v1_router.include_router(consent_router)
api_v1_router.include_router(system_router)
api_v1_router.include_router(realtime_router)
api_v1_router.include_router(interactions_router)
api_v1_router.include_router(notifications_router)
api_v1_router.include_router(clinical_guidance_router)

