from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.db.session import SessionLocal, engine, get_db
from app.db.init_db import init_db
from app.api.router import api_v1_router
from app.schemas.system import HealthCheckResponse
from app.realtime.manager import ws_manager, authenticate_websocket_sync
from fastapi import WebSocket, WebSocketDisconnect


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-flight environment and security validation (SEC-06, SEC-07, SEC-08)
    settings.validate_startup_security()

    # Startup Diagnostic: Log resolved database target and notification mode safely
    db_info = settings.get_sanitized_database_info()
    logger.info(
        f"LifeLink Database Target: dialect={db_info['dialect']}, "
        f"target={db_info['resolved_target']}, "
        f"canonical={db_info['is_canonical']}, "
        f"sandbox={db_info['is_sandbox']}"
    )
    if settings.DEMO_WRITE_GUARD_ENABLED:
        settings.assert_isolated_target_for_write_testing()
        logger.info("Demo write guard: ENFORCED (sandbox isolation verified).")
    
    logger.info(f"Notification Provider Mode: mock_only={settings.MOCK_NOTIFICATIONS_ONLY}")

    # Startup: Initialize Database Tables and Seeder
    logger.info("Initializing LifeLink Database Foundation...")
    db = SessionLocal()
    try:
        init_db(db)
        logger.info("LifeLink Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
    finally:
        db.close()
    yield
    # Shutdown: Clean up connections
    logger.info("Shutting down LifeLink backend...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="""
# LifeLink Healthcare Intelligence Platform — Phase 1 Backend Foundation

FastAPI REST and Real-Time WebSocket backend powering emergency healthcare intelligence:
1. **Blood Donor Emergency Response & Dynamic Radius Intelligence**
2. **Organ Availability, Reachability & Viability Intelligence**
3. **Ambulance Live Tracking, Routing & Hospital Bay Coordination**
4. **Role-Based Access Control (RBAC) & Tamper-Evident Audit Logging**
""",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ------------------------------------------------------------
# CORS Middleware (SEC-07)
# ------------------------------------------------------------
cors_origins = (
    [o for o in settings.CORS_ORIGINS if o != "*"]
    if settings.APP_ENV in ("staging", "production")
    else (settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else [settings.CORS_ORIGINS])
)
# W3C / Starlette security: Wildcard origins cannot be used when allow_credentials=True
allow_creds = True
if "*" in cors_origins:
    allow_creds = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_creds,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ------------------------------------------------------------
# Global Error Handling
# ------------------------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "code": "RATE_LIMIT_EXCEEDED" if exc.status_code == 429 else f"HTTP_{exc.status_code}",
            "message": exc.detail,
            "status": "error",
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": exc.errors(),
            "status": "error",
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An internal server error occurred.",
            "status": "error",
        },
    )


# ------------------------------------------------------------
# Health & Readiness Endpoints
# ------------------------------------------------------------
@app.get(
    "/health",
    response_model=HealthCheckResponse,
    tags=["System Health"],
    summary="Service Health Check",
    description="Returns the operational status of the LifeLink backend service.",
)
def health_check():
    return HealthCheckResponse(
        status="ok",
        service="lifelink-backend",
        version=settings.VERSION,
        environment=settings.APP_ENV,
        database="connected",
    )


@app.get(
    "/health/ready",
    tags=["System Health"],
    summary="Readiness Check",
    description="Verifies that the database and internal services are ready to accept traffic.",
)
def readiness_check(db: Session = Depends(get_db)):
    try:
        # Execute test query to confirm DB connection readiness
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "database": "connected",
            "service": "lifelink-backend",
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unready", "database": "disconnected", "error": str(e)},
        )


# ------------------------------------------------------------
# WebSocket Direct Gateway (/ws)
# ------------------------------------------------------------
@app.websocket("/ws")
async def root_websocket(websocket: WebSocket, db: Session = Depends(get_db)):
    user_info = authenticate_websocket_sync(websocket, db=db)
    if not user_info:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws_manager.connect(websocket, user_info=user_info)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


# ------------------------------------------------------------
# Router Inclusions
# ------------------------------------------------------------
app.include_router(api_v1_router)
