from typing import Optional, List
from pydantic import BaseModel, Field


class AmbulanceCoordinates(BaseModel):
    lat: float
    lng: float
    heading: Optional[float] = None


class RouteOptionSchema(BaseModel):
    id: str
    label: str
    distanceKm: float
    etaMinutes: int
    trafficCondition: str # light, normal, moderate, heavy, gridlock
    roadFeasibility: str # high, medium, low
    isAiRecommended: bool
    aiRationale: Optional[str] = None
    polyline: Optional[str] = None


class AmbulanceResponse(BaseModel):
    id: str
    unitNumber: str
    status: str # idle, dispatched, en_route, on_scene, transporting, at_hospital, returning, offline
    driverName: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    currentLocation: Optional[AmbulanceCoordinates] = None
    speedKmh: Optional[float] = None
    etaMinutes: Optional[int] = None
    routes: Optional[List[RouteOptionSchema]] = None
    selectedRouteId: Optional[str] = None
    hospitalId: str
    emergencyId: Optional[str] = None
    dispatchedAt: Optional[str] = None
    arrivedAt: Optional[str] = None
    telemetrySource: Optional[str] = "operator_manual"
    lastTelemetryAt: Optional[str] = None
    deviceId: Optional[str] = None
    isStale: Optional[bool] = False
    updatedAt: str


class AmbulanceLocationUpdate(BaseModel):
    lat: float
    lng: float
    heading: Optional[float] = None
    speedKmh: Optional[float] = None


class AmbulanceStatusUpdate(BaseModel):
    status: str
    selectedRouteId: Optional[str] = None


class AmbulanceEtaUpdate(BaseModel):
    ambulanceId: str
    previousEta: int
    newEta: int
    reason: str
    timestamp: str


class AmbulanceTelemetryIngest(BaseModel):
    ambulanceId: str
    deviceId: str
    lat: float = Field(..., ge=-90.0, le=90.0)
    lng: float = Field(..., ge=-180.0, le=180.0)
    heading: Optional[float] = Field(None, ge=0.0, le=360.0)
    speedKmh: Optional[float] = Field(None, ge=0.0, le=250.0)
    altitudeMeters: Optional[float] = None
    deviceTimestamp: str
    telemetrySource: Optional[str] = "live_gps" # "live_gps" or "simulated"


class AmbulanceTelemetryIngestResponse(BaseModel):
    status: str
    ambulanceId: str
    telemetrySource: str
    receivedAt: str
    deviceTimestamp: str
    currentLocation: AmbulanceCoordinates
    speedKmh: Optional[float] = None
    isDuplicate: bool = False

