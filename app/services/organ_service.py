import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.organ import Organ
from app.models.audit import AuditLog
from app.models.emergency import Emergency, EmergencyEvent
from app.models.hospital import Hospital
from app.schemas.organ import OrganResponse, ClinicalReviewRequest, OrganRequest, OrganRequestResponse
from app.schemas.emergency import EmergencyCreate
from app.schemas.donor import Coordinates
from app.schemas.auth import UserProfileSchema
from app.core.logging import logger


class OrganService:
    now_fn = staticmethod(lambda: datetime.now(timezone.utc))

    @staticmethod
    def parse_reference_timestamp(ts: Optional[str]) -> Optional[datetime]:
        """
        Parses an ISO 8601 timestamp string into a timezone-aware UTC datetime.
        Handles UTC 'Z', explicit timezone offsets (+/-HH:MM), and naive timestamps (assumed UTC).
        Returns None safely if string is missing, invalid, or unparseable.
        """
        if not ts or not isinstance(ts, str):
            return None
        try:
            clean = ts.strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception as e:
            logger.warning(f"Could not parse organ reference timestamp '{ts}': {e}")
            return None

    @staticmethod
    def calculate_dynamic_viability(
        total_seconds: int,
        available_at_str: Optional[str],
        fallback_remaining_seconds: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> int:
        """
        Dynamically computes cold ischemia remaining viability seconds:
        remaining = max(0, min(total_seconds, total_seconds - elapsed_seconds))
        where elapsed_seconds = now_utc - available_at_utc.

        Safe edge-case behaviors:
        - If total_seconds <= 0, returns 0.
        - If available_at is missing or unparseable, falls back to fallback_remaining_seconds
          (the stored viability_remaining_seconds), clamped to [0, total_seconds].
        - If fallback is also absent or invalid, safely defaults to 0 (conservative clinical safeguard).
        - If available_at is in the future, clamps remaining seconds to total_seconds.
        - Clamps expired values (elapsed >= total_seconds) at 0.
        """
        if total_seconds <= 0:
            return 0

        ref_dt = OrganService.parse_reference_timestamp(available_at_str)
        if ref_dt is None:
            if fallback_remaining_seconds is not None and fallback_remaining_seconds >= 0:
                return max(0, min(total_seconds, int(fallback_remaining_seconds)))
            return 0

        now_utc = now if now is not None else OrganService.now_fn()
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)
        else:
            now_utc = now_utc.astimezone(timezone.utc)

        elapsed_seconds = (now_utc - ref_dt).total_seconds()
        if elapsed_seconds < 0:
            return total_seconds

        remaining = int(total_seconds - elapsed_seconds)
        return max(0, min(total_seconds, remaining))

    @staticmethod
    def _map_organ_to_response(o: Organ, now: Optional[datetime] = None) -> OrganResponse:
        coords = None
        if o.lat is not None and o.lng is not None:
            coords = Coordinates(lat=o.lat, lng=o.lng)

        dynamic_remaining = OrganService.calculate_dynamic_viability(
            total_seconds=o.viability_total_seconds,
            available_at_str=o.available_at,
            fallback_remaining_seconds=o.viability_remaining_seconds,
            now=now,
        )

        return OrganResponse(
            id=o.id,
            organType=o.organ_type,
            sourceHospitalId=o.source_hospital_id,
            sourceHospitalName=o.source_hospital_name,
            distanceKm=o.distance_km,
            etaMinutes=o.eta_minutes,
            viabilityRemainingSeconds=dynamic_remaining,
            viabilityTotalSeconds=o.viability_total_seconds,
            viabilityLevel=o.viability_level,
            reachabilityScore=o.reachability_score,
            aiRecommendation=o.ai_recommendation,
            aiRationale=o.ai_rationale,
            status=o.status,
            clinicalReviewStatus=o.clinical_review_status,
            authorizedCoordinatorId=o.authorized_coordinator_id,
            coordinates=coords,
            availableAt=o.available_at,
            updatedAt=o.updated_at,
        )

    @staticmethod
    def get_all(db: Session, now: Optional[datetime] = None) -> List[OrganResponse]:
        organs = db.query(Organ).all()
        responses = [OrganService._map_organ_to_response(o, now=now) for o in organs]
        responses.sort(key=lambda r: r.viabilityRemainingSeconds)
        return responses

    @staticmethod
    def get_by_id(db: Session, organ_id: str, now: Optional[datetime] = None) -> OrganResponse:
        organ = db.query(Organ).filter(Organ.id == organ_id).first()
        if not organ:
            raise HTTPException(status_code=404, detail=f"Organ #{organ_id} not found")
        return OrganService._map_organ_to_response(organ, now=now)

    @staticmethod
    def request_clinical_review(
        db: Session,
        organ_id: str,
        current_user: UserProfileSchema,
        review_data: Optional[ClinicalReviewRequest] = None,
    ) -> OrganResponse:
        organ = db.query(Organ).filter(Organ.id == organ_id).first()
        if not organ:
            raise HTTPException(status_code=404, detail="Organ not found")

        now_str = datetime.now(timezone.utc).isoformat()
        organ.status = "clinical_review"
        organ.clinical_review_status = "in_review" if not review_data or not review_data.decision else review_data.decision
        organ.authorized_coordinator_id = current_user.id
        organ.updated_at = now_str

        # Create audit entry for clinical governance
        audit = AuditLog(
            id=f"audit-{uuid.uuid4().hex[:10]}",
            timestamp=now_str,
            actor=current_user.name,
            actor_type="user",
            action=f"Clinical review requested for {organ.organ_type.capitalize()} (Decision: {organ.clinical_review_status})",
            resource=f"Organ #{organ.id}",
            resource_id=organ.id,
            authorization=f"Role: {current_user.role}",
            status="success",
            module="organ",
        )
        db.add(audit)
        db.commit()
        db.refresh(organ)
        return OrganService._map_organ_to_response(organ)

    @staticmethod
    def create_organ_request(
        db: Session,
        req: OrganRequest,
        current_user: UserProfileSchema,
    ) -> OrganRequestResponse:
        # 1. Field validation
        organ_type = (req.organType or "").strip().lower()
        if not organ_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target organ type is required",
            )

        valid_organ_types = {
            "kidney", "liver", "heart", "lung", "pancreas", "cornea", "bone_marrow", "tissues"
        }
        if organ_type not in valid_organ_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid organ type '{req.organType}'. Valid types: {', '.join(sorted(valid_organ_types))}",
            )

        hospital_id = (req.recipientHospitalId or "").strip()
        if not hospital_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Recipient hospital identifier is required",
            )

        # 2. Recipient hospital validation
        hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
        if not hospital:
            now_str = datetime.now(timezone.utc).isoformat()
            audit = AuditLog(
                id=f"audit-err-{uuid.uuid4().hex[:10]}",
                timestamp=now_str,
                actor=current_user.name,
                actor_type="user",
                action=f"Failed to create Organ Alert Search: Unknown hospital ID '{hospital_id}'",
                resource=f"Hospital #{hospital_id}",
                resource_id=hospital_id,
                authorization=f"Role: {current_user.role}",
                status="failed",
                module="organ",
            )
            db.add(audit)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Hospital with ID '{hospital_id}' not found",
            )

        # 3. Urgency to priority mapping
        urgency_raw = (req.urgency or "critical").strip().lower()
        priority_map = {
            "critical": "critical",
            "urgent": "high",
            "standard": "medium",
            "high": "high",
            "medium": "medium",
            "low": "low",
        }
        priority = priority_map.get(urgency_raw, "critical")

        # 4. Idempotency / Duplicate request check (same organ type & hospital within 60s)
        recent_cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        existing = (
            db.query(Emergency)
            .filter(
                Emergency.type == "organ",
                Emergency.organ_type == organ_type,
                Emergency.hospital_id == hospital_id,
                Emergency.status.in_(["created", "searching", "coordinating", "in_progress"]),
                Emergency.created_at >= recent_cutoff,
            )
            .order_by(Emergency.created_at.desc())
            .first()
        )
        if existing:
            return OrganRequestResponse(
                id=existing.id,
                emergencyId=existing.id,
                status=existing.status,
                organType=existing.organ_type or organ_type,
                recipientHospitalId=existing.hospital_id,
                recipientHospitalName=existing.hospital_name,
                urgency=urgency_raw,
                priority=existing.priority,
                createdAt=existing.created_at,
                notes=existing.description,
                eta=existing.eta or 15,
            )

        # 5. Atomic persistence via EmergencyService
        from app.services.emergency_service import EmergencyService
        desc = (
            req.notes.strip()
            if req.notes and req.notes.strip()
            else f"Emergency organ match search for {organ_type.capitalize()} at {hospital.name}"
        )
        create_data = EmergencyCreate(
            type="organ",
            priority=priority,
            status="searching",
            hospitalId=hospital_id,
            hospitalName=hospital.name,
            organType=organ_type,
            description=desc,
        )
        try:
            emergency_res = EmergencyService.create(db, create_data, current_user)
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to persist organ emergency request: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to persist organ emergency request: {str(e)}",
            )

        return OrganRequestResponse(
            id=emergency_res.id,
            emergencyId=emergency_res.id,
            status=emergency_res.status,
            organType=emergency_res.organType or organ_type,
            recipientHospitalId=emergency_res.hospitalId,
            recipientHospitalName=emergency_res.hospitalName,
            urgency=urgency_raw,
            priority=emergency_res.priority,
            createdAt=emergency_res.createdAt,
            notes=req.notes,
            eta=emergency_res.eta,
        )


organ_service = OrganService()
