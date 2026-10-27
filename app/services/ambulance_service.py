import json
import math
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Set
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.ambulance import Ambulance
from app.models.audit import AuditLog
from app.schemas.ambulance import (
    AmbulanceResponse,
    AmbulanceCoordinates,
    RouteOptionSchema,
    AmbulanceLocationUpdate,
    AmbulanceStatusUpdate,
    AmbulanceTelemetryIngest,
    AmbulanceTelemetryIngestResponse,
)
from app.schemas.auth import UserProfileSchema
from app.core.permissions import UserRole
from app.core.logging import logger
from app.realtime.manager import ws_manager
from app.realtime.events import RealtimeEvent, RealtimeEventType


VALID_AMBULANCE_STATUSES: Set[str] = {
    "idle",
    "dispatched",
    "en_route",
    "on_scene",
    "transporting",
    "at_hospital",
    "returning",
    "offline",
}


def calculate_haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two GPS coordinates in kilometers."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


class AmbulanceService:
    @staticmethod
    def _map_ambulance_to_response(a: Ambulance) -> AmbulanceResponse:
        coords = None
        if a.lat is not None and a.lng is not None:
            coords = AmbulanceCoordinates(lat=a.lat, lng=a.lng, heading=a.heading)

        routes = []
        if a.routes_json:
            try:
                raw_routes = json.loads(a.routes_json)
                routes = [RouteOptionSchema(**r) for r in raw_routes]
            except Exception:
                pass

        # Compute staleness based on last telemetry timestamp
        is_stale = False
        last_tel = getattr(a, "last_telemetry_at", None)
        if last_tel:
            try:
                tel_dt = datetime.fromisoformat(last_tel.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - tel_dt > timedelta(minutes=5):
                    is_stale = True
            except Exception:
                pass

        return AmbulanceResponse(
            id=a.id,
            unitNumber=a.unit_number,
            status=a.status,
            driverName=a.driver_name,
            origin=a.origin,
            destination=a.destination,
            currentLocation=coords,
            speedKmh=a.speed_kmh,
            etaMinutes=a.eta_minutes,
            routes=routes,
            selectedRouteId=a.selected_route_id,
            hospitalId=a.hospital_id,
            emergencyId=a.emergency_id,
            dispatchedAt=a.dispatched_at,
            arrivedAt=a.arrived_at,
            telemetrySource=getattr(a, "telemetry_source", "operator_manual") or "operator_manual",
            lastTelemetryAt=last_tel,
            deviceId=getattr(a, "device_id", None),
            isStale=is_stale,
            updatedAt=a.updated_at,
        )

    @staticmethod
    def get_all(db: Session) -> List[AmbulanceResponse]:
        ambulances = db.query(Ambulance).all()
        return [AmbulanceService._map_ambulance_to_response(a) for a in ambulances]

    @staticmethod
    def get_by_id(db: Session, ambulance_id: str) -> AmbulanceResponse:
        a = db.query(Ambulance).filter(Ambulance.id == ambulance_id).first()
        if not a:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ambulance #{ambulance_id} not found",
            )
        return AmbulanceService._map_ambulance_to_response(a)

    @staticmethod
    def get_routes(db: Session, ambulance_id: str) -> List[RouteOptionSchema]:
        a = db.query(Ambulance).filter(Ambulance.id == ambulance_id).first()
        if not a:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ambulance #{ambulance_id} not found",
            )
        if not a.routes_json:
            return []
        try:
            return [RouteOptionSchema(**r) for r in json.loads(a.routes_json)]
        except Exception:
            return []

    @staticmethod
    def update_location(
        db: Session,
        ambulance_id: str,
        data: AmbulanceLocationUpdate,
        current_user: UserProfileSchema,
    ) -> AmbulanceResponse:
        # RBAC Check: donors and patients cannot update telemetry
        if current_user.role in [UserRole.DONOR.value, UserRole.PATIENT.value]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized: Donors and patients cannot update ambulance location",
            )

        if current_user.role in [UserRole.AMBULANCE_OPERATOR.value, UserRole.AMBULANCE_DRIVER.value]:
            if current_user.verificationStatus == "rejected":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Professional account has been rejected by administration.",
                )
            if current_user.verificationStatus == "pending" or not current_user.isVerified:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Professional account pending verification. Please await administrator approval.",
                )



        # Coordinate bounds validation
        if not (-90.0 <= data.lat <= 90.0) or not (-180.0 <= data.lng <= 180.0):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid GPS coordinates: lat={data.lat}, lng={data.lng}",
            )

        a = db.query(Ambulance).filter(Ambulance.id == ambulance_id).first()
        if not a:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ambulance #{ambulance_id} not found",
            )

        # No-op check: avoid excessive telemetry broadcasts for unchanged coordinates
        is_noop = (
            a.lat == data.lat
            and a.lng == data.lng
            and (data.heading is None or a.heading == data.heading)
            and (data.speedKmh is None or a.speed_kmh == data.speedKmh)
        )
        if is_noop:
            return AmbulanceService._map_ambulance_to_response(a)

        a.lat = data.lat
        a.lng = data.lng
        if data.heading is not None:
            a.heading = data.heading
        if data.speedKmh is not None:
            a.speed_kmh = data.speedKmh
        a.telemetry_source = "operator_manual"
        now_iso = datetime.now(timezone.utc).isoformat()
        a.last_telemetry_at = now_iso
        a.updated_at = now_iso

        try:
            db.commit()
            db.refresh(a)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to commit ambulance location update: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while saving ambulance location",
            )

        # Post-commit telemetry broadcast
        try:
            ws_manager.broadcast_sync(
                RealtimeEvent(
                    type=RealtimeEventType.AMBULANCE_LOCATION_UPDATED.value,
                    payload={
                        "ambulanceId": a.id,
                        "unitNumber": a.unit_number,
                        "currentLocation": {
                            "lat": a.lat,
                            "lng": a.lng,
                            "heading": a.heading,
                        },
                        "speedKmh": a.speed_kmh,
                        "telemetrySource": a.telemetry_source,
                        "lastTelemetryAt": a.last_telemetry_at,
                        "isStale": False,
                        "updatedAt": a.updated_at,
                    },
                )
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast ambulance location telemetry: {e}")

        return AmbulanceService._map_ambulance_to_response(a)

    @staticmethod
    def ingest_telemetry(
        db: Session,
        data: AmbulanceTelemetryIngest,
        current_user: UserProfileSchema,
    ) -> AmbulanceTelemetryIngestResponse:
        # 1. RBAC check: only operational, medical, and device-authenticated callers can ingest telemetry
        if current_user.role in [UserRole.DONOR.value, UserRole.PATIENT.value]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized: Telemetry ingestion is restricted to verified operators and devices",
            )

        if current_user.role in [UserRole.AMBULANCE_OPERATOR.value, UserRole.AMBULANCE_DRIVER.value]:
            if current_user.verificationStatus == "rejected":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Professional account has been rejected by administration.",
                )
            if current_user.verificationStatus == "pending" or not current_user.isVerified:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Professional account pending verification. Please await administrator approval.",
                )


        # 2. Ambulance existence check
        a = db.query(Ambulance).filter(Ambulance.id == data.ambulanceId).first()
        if not a:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ambulance #{data.ambulanceId} not found",
            )

        # 3. Coordinate bounds validation
        if not (-90.0 <= data.lat <= 90.0) or not (-180.0 <= data.lng <= 180.0):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid GPS coordinates: lat={data.lat}, lng={data.lng}",
            )

        # 4. Device timestamp validation and parsing
        try:
            device_dt = datetime.fromisoformat(data.deviceTimestamp.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid device timestamp format. Expected ISO-8601 string.",
            )

        now = datetime.now(timezone.utc)
        if device_dt > now + timedelta(minutes=5):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Device timestamp is in the future. Check device clock synchronization.",
            )
        if device_dt < now - timedelta(hours=24):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Device telemetry is too stale (> 24 hours old). Telemetry rejected.",
            )

        # 5. Out-of-order and duplicate checks
        last_tel = getattr(a, "last_telemetry_at", None)
        if last_tel:
            try:
                last_dt = datetime.fromisoformat(last_tel.replace("Z", "+00:00"))
                if device_dt <= last_dt:
                    # Check if identical coordinates -> duplicate acknowledge
                    if a.lat == data.lat and a.lng == data.lng:
                        return AmbulanceTelemetryIngestResponse(
                            status="accepted",
                            ambulanceId=a.id,
                            telemetrySource=data.telemetrySource or "live_gps",
                            receivedAt=now.isoformat(),
                            deviceTimestamp=data.deviceTimestamp,
                            currentLocation=AmbulanceCoordinates(lat=a.lat, lng=a.lng, heading=a.heading),
                            speedKmh=a.speed_kmh,
                            isDuplicate=True,
                        )
                    # Out-of-order update with differing coordinates
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Out-of-order telemetry: Device timestamp is older than last recorded telemetry.",
                    )
            except HTTPException:
                raise
            except Exception:
                pass

        # 6. Implausible coordinate jump validation
        if a.lat is not None and a.lng is not None and last_tel:
            try:
                last_dt = datetime.fromisoformat(last_tel.replace("Z", "+00:00"))
                delta_seconds = (device_dt - last_dt).total_seconds()
                if 0 < delta_seconds < 60:
                    distance_km = calculate_haversine_km(a.lat, a.lng, data.lat, data.lng)
                    calculated_speed_kmh = distance_km / (delta_seconds / 3600.0)
                    if calculated_speed_kmh > 300.0:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Implausible coordinate jump detected: calculated speed {calculated_speed_kmh:.1f} km/h exceeds vehicle limits.",
                        )
            except HTTPException:
                raise
            except Exception:
                pass

        # 7. No-op duplicate check
        is_noop = (
            a.lat == data.lat
            and a.lng == data.lng
            and (data.heading is None or a.heading == data.heading)
            and (data.speedKmh is None or a.speed_kmh == data.speedKmh)
        )
        if is_noop:
            return AmbulanceTelemetryIngestResponse(
                status="accepted",
                ambulanceId=a.id,
                telemetrySource=data.telemetrySource or "live_gps",
                receivedAt=now.isoformat(),
                deviceTimestamp=data.deviceTimestamp,
                currentLocation=AmbulanceCoordinates(lat=a.lat, lng=a.lng, heading=a.heading),
                speedKmh=a.speed_kmh,
                isDuplicate=True,
            )

        # 8. Persistence
        a.lat = data.lat
        a.lng = data.lng
        if data.heading is not None:
            a.heading = data.heading
        if data.speedKmh is not None:
            a.speed_kmh = data.speedKmh
        a.telemetry_source = data.telemetrySource or "live_gps"
        a.last_telemetry_at = data.deviceTimestamp
        a.device_id = data.deviceId
        a.updated_at = now.isoformat()

        try:
            db.commit()
            db.refresh(a)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to commit ambulance telemetry ingestion: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while persisting ambulance telemetry",
            )

        # 9. Post-commit WebSocket broadcast
        try:
            ws_manager.broadcast_sync(
                RealtimeEvent(
                    type=RealtimeEventType.AMBULANCE_LOCATION_UPDATED.value,
                    payload={
                        "ambulanceId": a.id,
                        "unitNumber": a.unit_number,
                        "currentLocation": {
                            "lat": a.lat,
                            "lng": a.lng,
                            "heading": a.heading,
                        },
                        "speedKmh": a.speed_kmh,
                        "telemetrySource": a.telemetry_source,
                        "lastTelemetryAt": a.last_telemetry_at,
                        "isStale": False,
                        "updatedAt": a.updated_at,
                    },
                )
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast ambulance location telemetry: {e}")

        return AmbulanceTelemetryIngestResponse(
            status="accepted",
            ambulanceId=a.id,
            telemetrySource=a.telemetry_source,
            receivedAt=now.isoformat(),
            deviceTimestamp=data.deviceTimestamp,
            currentLocation=AmbulanceCoordinates(lat=a.lat, lng=a.lng, heading=a.heading),
            speedKmh=a.speed_kmh,
            isDuplicate=False,
        )

    @staticmethod
    def update_status(
        db: Session,
        ambulance_id: str,
        data: AmbulanceStatusUpdate,
        current_user: UserProfileSchema,
    ) -> AmbulanceResponse:
        # RBAC Check: donors and patients cannot update ambulance dispatch status
        if current_user.role in [UserRole.DONOR.value, UserRole.PATIENT.value]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized: Donors and patients cannot update ambulance status",
            )

        if current_user.role in [UserRole.AMBULANCE_OPERATOR.value, UserRole.AMBULANCE_DRIVER.value]:
            if current_user.verificationStatus == "rejected":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Professional account has been rejected by administration.",
                )
            if current_user.verificationStatus == "pending" or not current_user.isVerified:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Professional account pending verification. Please await administrator approval.",
                )


        normalized_status = data.status.strip().lower()
        if normalized_status not in VALID_AMBULANCE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid ambulance status '{data.status}'. Valid statuses: {', '.join(sorted(VALID_AMBULANCE_STATUSES))}",
            )

        a = db.query(Ambulance).filter(Ambulance.id == ambulance_id).first()
        if not a:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ambulance #{ambulance_id} not found",
            )

        # No-op check: skip duplicate audit logging and broadcast if unchanged
        is_noop = (
            a.status == normalized_status
            and (data.selectedRouteId is None or a.selected_route_id == data.selectedRouteId)
        )
        if is_noop:
            return AmbulanceService._map_ambulance_to_response(a)

        previous_status = a.status
        a.status = normalized_status
        if data.selectedRouteId:
            a.selected_route_id = data.selectedRouteId
        now_str = datetime.now(timezone.utc).isoformat()
        a.updated_at = now_str

        # Collision-resistant UUID-based audit identifier
        audit_id = f"audit-{uuid.uuid4().hex[:10]}"
        audit = AuditLog(
            id=audit_id,
            timestamp=now_str,
            actor=current_user.name,
            actor_type="user",
            action=f"Ambulance {a.unit_number} status updated to '{normalized_status}'",
            resource=f"Ambulance {a.unit_number}",
            resource_id=a.id,
            authorization=f"Role: {current_user.role}",
            status="success",
            module="ambulance",
            metadata_json=json.dumps({
                "ambulanceId": a.id,
                "unitNumber": a.unit_number,
                "previousStatus": previous_status,
                "newStatus": normalized_status,
                "selectedRouteId": a.selected_route_id,
            }),
        )
        db.add(audit)

        try:
            db.commit()
            db.refresh(a)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to commit ambulance status update: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while saving ambulance status",
            )

        # Post-commit telemetry broadcast
        try:
            ws_manager.broadcast_sync(
                RealtimeEvent(
                    type=RealtimeEventType.AMBULANCE_STATUS_UPDATED.value,
                    payload={
                        "ambulanceId": a.id,
                        "unitNumber": a.unit_number,
                        "status": a.status,
                        "selectedRouteId": a.selected_route_id,
                        "hospitalId": a.hospital_id,
                        "emergencyId": a.emergency_id,
                        "updatedAt": a.updated_at,
                    },
                )
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast ambulance status telemetry: {e}")

        return AmbulanceService._map_ambulance_to_response(a)


ambulance_service = AmbulanceService()
