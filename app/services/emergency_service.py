import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.emergency import Emergency, EmergencyEvent
from app.models.hospital import Hospital
from app.models.user import User
from app.models.audit import AuditLog
from app.schemas.emergency import EmergencyCreate, EmergencyUpdate, EmergencyResponse, EmergencyEventResponse, KPIDataResponse
from app.schemas.auth import UserProfileSchema
from app.core.permissions import UserRole
from app.core.logging import logger
from app.realtime.manager import ws_manager
from app.realtime.events import RealtimeEvent, RealtimeEventType


class EmergencyService:
    @staticmethod
    def _map_emergency_to_response(e: Emergency) -> EmergencyResponse:
        resource_ids = []
        if e.assigned_resource_ids:
            try:
                resource_ids = json.loads(e.assigned_resource_ids)
            except Exception:
                resource_ids = [r.strip() for r in e.assigned_resource_ids.split(",") if r.strip()]

        return EmergencyResponse(
            id=e.id,
            patientId=e.patient_id,
            type=e.type,
            priority=e.priority,
            status=e.status,
            hospitalId=e.hospital_id,
            hospitalName=e.hospital_name,
            createdAt=e.created_at,
            updatedAt=e.updated_at,
            description=e.description,
            eta=e.eta,
            assignedResourceIds=resource_ids,
            resolvedAt=e.resolved_at,
            bloodGroup=e.blood_group,
            unitsRequired=e.units_required,
            organType=e.organ_type,
            origin=e.origin,
            destination=e.destination,
            locationLat=getattr(e, "location_lat", None),
            locationLng=getattr(e, "location_lng", None),
        )

    @staticmethod
    def get_all(
        db: Session,
        current_user: Optional[UserProfileSchema] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        blood_group: Optional[str] = None,
        emergency_type: Optional[str] = None,
        hospital_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[EmergencyResponse]:
        query = db.query(Emergency)
        if current_user:
            if current_user.role == UserRole.PATIENT.value:
                query = query.filter(Emergency.patient_id == current_user.id)
            elif current_user.role == UserRole.DONOR.value:
                # Donors are not authorized to browse emergency lists
                return []
            elif current_user.role == UserRole.HOSPITAL_STAFF.value and current_user.hospitalId:
                # Hospital staff restricted to emergencies of their assigned hospital
                query = query.filter(Emergency.hospital_id == current_user.hospitalId)

        if status:
            query = query.filter(Emergency.status == status.strip().lower())
        if priority:
            query = query.filter(Emergency.priority == priority.strip().lower())
        if blood_group:
            query = query.filter(Emergency.blood_group == blood_group.strip().upper())
        if emergency_type:
            query = query.filter(Emergency.type == emergency_type.strip().lower())
        if hospital_id:
            query = query.filter(Emergency.hospital_id == hospital_id.strip())

        emergencies = query.order_by(Emergency.created_at.desc()).offset(max(0, skip)).limit(min(max(1, limit), 100)).all()
        return [EmergencyService._map_emergency_to_response(e) for e in emergencies]

    @staticmethod
    def get_by_id(db: Session, emergency_id: str, current_user: Optional[UserProfileSchema] = None) -> EmergencyResponse:
        e = db.query(Emergency).filter(Emergency.id == emergency_id).first()
        if not e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Emergency with ID '{emergency_id}' not found",
            )
        if current_user:
            if current_user.role == UserRole.PATIENT.value:
                if e.patient_id != current_user.id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access forbidden: You are not authorized to view this emergency record",
                    )
            elif current_user.role == UserRole.DONOR.value:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access forbidden: Donors cannot directly view emergency records",
                )
            elif current_user.role == UserRole.HOSPITAL_STAFF.value and current_user.hospitalId:
                if e.hospital_id and e.hospital_id != current_user.hospitalId:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access forbidden: Hospital staff can only view emergencies for their assigned hospital",
                    )
        return EmergencyService._map_emergency_to_response(e)

    @staticmethod
    def get_patient_emergency(db: Session, current_user: UserProfileSchema) -> Optional[EmergencyResponse]:
        """Fetches the active emergency securely linked to the authenticated patient."""
        e = (
            db.query(Emergency)
            .filter(
                Emergency.patient_id == current_user.id,
                Emergency.status.in_(["created", "searching", "coordinating", "active", "dispatched", "en_route"]),
            )
            .order_by(Emergency.created_at.desc())
            .first()
        )
        if not e:
            return None
        return EmergencyService._map_emergency_to_response(e)

    @staticmethod
    def create(db: Session, data: EmergencyCreate, current_user: UserProfileSchema) -> EmergencyResponse:
        # Generate emergency ID based on type
        prefix = "BL" if data.type == "blood" else "ORG" if data.type == "organ" else "AMB"
        emergency_id = f"{prefix}-{uuid.uuid4().hex[:6].upper()}"

        now_str = datetime.now(timezone.utc).isoformat()

        # Validate hospital reference
        h_id: str
        h_name: str
        if data.hospitalId:
            hospital = db.query(Hospital).filter(Hospital.id == data.hospitalId).first()
            if not hospital:
                # Failure audit log
                audit = AuditLog(
                    id=f"audit-err-{uuid.uuid4().hex[:10]}",
                    timestamp=now_str,
                    actor=current_user.name,
                    actor_type="user",
                    action=f"Failed to create {data.type.capitalize()} Emergency: Unknown hospital ID '{data.hospitalId}'",
                    resource=f"Hospital #{data.hospitalId}",
                    resource_id=data.hospitalId,
                    authorization=f"Role: {current_user.role}",
                    status="failed",
                    module=data.type if data.type in ["blood", "organ", "ambulance"] else "system",
                )
                db.add(audit)
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Hospital with ID '{data.hospitalId}' not found",
                )
            h_id = hospital.id
            h_name = hospital.name
        elif data.type in ["blood", "organ"]:
            # Blood and organ emergencies legitimately require a clinical hospital facility
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Hospital ID is required for {data.type} emergencies",
            )
        else:
            # For general transport/ambulance emergencies where hospital is not explicitly specified:
            fallback_hid = getattr(current_user, "hospital_id", None) or "city-hospital-001"
            fallback_hosp = db.query(Hospital).filter(Hospital.id == fallback_hid).first()
            h_id = fallback_hosp.id if fallback_hosp else fallback_hid
            h_name = fallback_hosp.name if fallback_hosp else (data.hospitalName or "City General Hospital")

        # Determine patient linkage:
        assigned_patient_id: Optional[str] = None
        if current_user.role == UserRole.PATIENT.value:
            assigned_patient_id = current_user.id
        elif data.patientId:
            patient_user = db.query(User).filter(User.id == data.patientId).first()
            if not patient_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Patient user '{data.patientId}' not found",
                )
            assigned_patient_id = patient_user.id

        initial_status = data.status if data.status else ("searching" if data.type == "organ" else "created")
        emergency = Emergency(
            id=emergency_id,
            patient_id=assigned_patient_id,
            type=data.type,
            priority=data.priority,
            status=initial_status,
            hospital_id=h_id,
            hospital_name=h_name,
            created_at=now_str,
            updated_at=now_str,
            description=data.description,
            eta=10 if data.type == "blood" else 15,
            blood_group=data.bloodGroup,
            units_required=data.unitsRequired,
            organ_type=data.organType,
            origin=data.origin,
            destination=data.destination,
            location_lat=data.locationLat,
            location_lng=data.locationLng,
        )
        db.add(emergency)

        # Create initial audit log & timeline event
        event = EmergencyEvent(
            id=f"evt-{uuid.uuid4().hex[:10]}",
            emergency_id=emergency_id,
            timestamp=now_str,
            actor=current_user.name,
            action=f"Emergency created: {data.type.upper()} ({data.priority.upper()})",
            resource=f"Emergency #{emergency_id}",
            authorization=f"Role: {current_user.role}",
            status="success",
        )
        db.add(event)

        audit = AuditLog(
            id=f"audit-{uuid.uuid4().hex[:10]}",
            timestamp=now_str,
            actor=current_user.name,
            actor_type="user",
            action=f"Created {data.type.capitalize()} Emergency SOS",
            resource=f"Emergency #{emergency_id}",
            resource_id=emergency_id,
            authorization=f"Role: {current_user.role}",
            status="success",
            module=data.type if data.type in ["blood", "organ", "ambulance"] else "system",
        )
        db.add(audit)

        try:
            db.commit()
            db.refresh(emergency)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to commit emergency creation: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error occurred while creating emergency",
            )

        try:
            from app.realtime.manager import ws_manager
            from app.realtime.events import RealtimeEvent, RealtimeEventType
            ws_manager.broadcast_sync(
                RealtimeEvent(
                    type=RealtimeEventType.EMERGENCY_CREATED.value,
                    payload={
                        "emergencyId": emergency.id,
                        "type": emergency.type,
                        "organType": emergency.organ_type,
                        "priority": emergency.priority,
                        "status": emergency.status,
                        "hospitalId": emergency.hospital_id,
                        "hospitalName": emergency.hospital_name,
                    },
                )
            )
        except Exception:
            pass

        return EmergencyService._map_emergency_to_response(emergency)

    @staticmethod
    def update(db: Session, emergency_id: str, data: EmergencyUpdate, current_user: UserProfileSchema) -> EmergencyResponse:
        e = db.query(Emergency).filter(Emergency.id == emergency_id).first()
        if not e:
            raise HTTPException(status_code=404, detail="Emergency not found")

        # Authorization: Donors and patients cannot modify emergencies
        if current_user.role in [UserRole.DONOR.value, UserRole.PATIENT.value]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized: Donors and patients cannot modify emergencies",
            )

        # Hospital staff can only modify emergencies for their assigned hospital
        if current_user.role == UserRole.HOSPITAL_STAFF.value and current_user.hospitalId:
            if e.hospital_id and e.hospital_id != current_user.hospitalId:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Unauthorized: Hospital staff can only modify emergencies for their assigned hospital",
                )

        if data.priority is not None:
            e.priority = data.priority
        if data.status is not None:
            e.status = data.status
        if data.eta is not None:
            e.eta = data.eta
        if data.description is not None:
            e.description = data.description
        if data.locationLat is not None:
            e.location_lat = data.locationLat
        if data.locationLng is not None:
            e.location_lng = data.locationLng

        e.updated_at = datetime.now(timezone.utc).isoformat()
        db.commit()
        db.refresh(e)

        try:
            from app.realtime.manager import ws_manager
            from app.realtime.events import RealtimeEvent, RealtimeEventType
            ws_manager.broadcast_sync(
                RealtimeEvent(
                    type=RealtimeEventType.EMERGENCY_UPDATED.value,
                    payload={
                        "emergencyId": e.id,
                        "type": e.type,
                        "priority": e.priority,
                        "status": e.status,
                        "action": "updated",
                        "eta": e.eta,
                    },
                )
            )
        except Exception:
            pass

        return EmergencyService._map_emergency_to_response(e)

    @staticmethod
    def resolve(db: Session, emergency_id: str, current_user: UserProfileSchema) -> EmergencyResponse:
        e = db.query(Emergency).filter(Emergency.id == emergency_id).first()
        if not e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Emergency with ID '{emergency_id}' not found",
            )

        # RBAC validation: only clinical/administrative staff can resolve emergencies
        if current_user.role in [UserRole.DONOR.value, UserRole.PATIENT.value]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized: Donors and patients cannot resolve emergencies",
            )

        # Idempotency / Retry Check: If already resolved, return without duplicate events
        if e.status == "resolved":
            return EmergencyService._map_emergency_to_response(e)

        # State Transition Validation: Cannot resolve an emergency that is already cancelled
        if e.status == "cancelled":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot resolve emergency '{emergency_id}' because it has already been cancelled",
            )

        now_str = datetime.now(timezone.utc).isoformat()
        e.status = "resolved"
        e.resolved_at = now_str
        e.updated_at = now_str

        # EmergencyEvent timeline entry
        event = EmergencyEvent(
            id=f"evt-{uuid.uuid4().hex[:10]}",
            emergency_id=e.id,
            timestamp=now_str,
            actor=current_user.name,
            action=f"Emergency resolved: {e.type.upper()} ({e.priority.upper()})",
            resource=f"Emergency #{e.id}",
            authorization=f"Role: {current_user.role}",
            status="success",
        )
        db.add(event)

        # AuditLog compliance entry
        audit = AuditLog(
            id=f"audit-{uuid.uuid4().hex[:10]}",
            timestamp=now_str,
            actor=current_user.name,
            actor_type="user",
            action=f"Resolved {e.type.capitalize()} Emergency SOS",
            resource=f"Emergency #{e.id}",
            resource_id=e.id,
            authorization=f"Role: {current_user.role}",
            status="success",
            module=e.type if e.type in ["blood", "organ", "ambulance"] else "system",
        )
        db.add(audit)

        try:
            db.commit()
            db.refresh(e)
        except Exception:
            db.rollback()
            raise

        try:
            from app.realtime.manager import ws_manager
            from app.realtime.events import RealtimeEvent, RealtimeEventType
            ws_manager.broadcast_sync(
                RealtimeEvent(
                    type=RealtimeEventType.EMERGENCY_UPDATED.value,
                    payload={
                        "emergencyId": e.id,
                        "type": e.type,
                        "priority": e.priority,
                        "status": "resolved",
                        "action": "resolved",
                        "resolvedAt": e.resolved_at,
                    },
                )
            )
        except Exception:
            pass

        return EmergencyService._map_emergency_to_response(e)

    @staticmethod
    def cancel(db: Session, emergency_id: str, current_user: UserProfileSchema) -> EmergencyResponse:
        e = db.query(Emergency).filter(Emergency.id == emergency_id).first()
        if not e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Emergency with ID '{emergency_id}' not found",
            )

        # RBAC validation: only clinical/administrative staff can cancel emergencies
        if current_user.role in [UserRole.DONOR.value, UserRole.PATIENT.value]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized: Donors and patients cannot cancel emergencies",
            )

        # Idempotency / Retry Check: If already cancelled, return without duplicate events
        if e.status == "cancelled":
            return EmergencyService._map_emergency_to_response(e)

        # State Transition Validation: Cannot cancel an emergency that is already resolved
        if e.status == "resolved":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel emergency '{emergency_id}' because it has already been resolved",
            )

        now_str = datetime.now(timezone.utc).isoformat()
        e.status = "cancelled"
        e.updated_at = now_str

        # EmergencyEvent timeline entry
        event = EmergencyEvent(
            id=f"evt-{uuid.uuid4().hex[:10]}",
            emergency_id=e.id,
            timestamp=now_str,
            actor=current_user.name,
            action=f"Emergency cancelled: {e.type.upper()} ({e.priority.upper()})",
            resource=f"Emergency #{e.id}",
            authorization=f"Role: {current_user.role}",
            status="success",
        )
        db.add(event)

        # AuditLog compliance entry
        audit = AuditLog(
            id=f"audit-{uuid.uuid4().hex[:10]}",
            timestamp=now_str,
            actor=current_user.name,
            actor_type="user",
            action=f"Cancelled {e.type.capitalize()} Emergency SOS",
            resource=f"Emergency #{e.id}",
            resource_id=e.id,
            authorization=f"Role: {current_user.role}",
            status="success",
            module=e.type if e.type in ["blood", "organ", "ambulance"] else "system",
        )
        db.add(audit)

        try:
            db.commit()
            db.refresh(e)
        except Exception:
            db.rollback()
            raise

        try:
            from app.realtime.manager import ws_manager
            from app.realtime.events import RealtimeEvent, RealtimeEventType
            ws_manager.broadcast_sync(
                RealtimeEvent(
                    type=RealtimeEventType.EMERGENCY_UPDATED.value,
                    payload={
                        "emergencyId": e.id,
                        "type": e.type,
                        "priority": e.priority,
                        "status": "cancelled",
                        "action": "cancelled",
                    },
                )
            )
        except Exception:
            pass

        return EmergencyService._map_emergency_to_response(e)

    @staticmethod
    def get_kpis(db: Session) -> KPIDataResponse:
        active_count = db.query(Emergency).filter(
            Emergency.status.notin_(["resolved", "cancelled"])
        ).count()
        blood_count = db.query(Emergency).filter(
            Emergency.type == "blood",
            Emergency.status.notin_(["resolved", "cancelled"])
        ).count()
        organ_count = db.query(Emergency).filter(
            Emergency.type == "organ",
            Emergency.status.notin_(["resolved", "cancelled"])
        ).count()

        return KPIDataResponse(
            activeEmergencies=active_count,
            bloodRequests=blood_count,
            organAlerts=organ_count,
            ambulancesActive=4,
            avgResponseTimeSeconds=258,
            donorAcceptanceRate=72,
        )

    @staticmethod
    def get_timeline(db: Session, emergency_id: Optional[str] = None) -> List[EmergencyEventResponse]:
        query = db.query(EmergencyEvent)
        if emergency_id:
            query = query.filter(EmergencyEvent.emergency_id == emergency_id)
        events = query.order_by(EmergencyEvent.timestamp.desc()).all()

        return [
            EmergencyEventResponse(
                id=evt.id,
                emergencyId=evt.emergency_id,
                timestamp=evt.timestamp,
                actor=evt.actor,
                action=evt.action,
                resource=evt.resource,
                authorization=evt.authorization,
                status=evt.status,
                metadata=json.loads(evt.metadata_json) if evt.metadata_json else None,
            )
            for evt in events
        ]


emergency_service = EmergencyService()
