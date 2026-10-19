import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.consent import Consent
from app.models.audit import AuditLog
from app.schemas.consent import ConsentResponse, ConsentUpdateRequest
from app.schemas.auth import UserProfileSchema


class ConsentService:
    @staticmethod
    def _map_consent(c: Consent) -> ConsentResponse:
        return ConsentResponse(
            id=c.id,
            userId=c.user_id,
            liveLocation=c.live_location,
            emergencyCommunication=c.emergency_communication,
            donationRequests=c.donation_requests,
            healthDataSharing=c.health_data_sharing,
            updatedAt=c.updated_at,
        )

    @staticmethod
    def get_user_consent(db: Session, user_id: str) -> ConsentResponse:
        c = db.query(Consent).filter(Consent.user_id == user_id).first()
        if not c:
            now_str = datetime.now(timezone.utc).isoformat()
            c = Consent(
                id=f"cns-{uuid.uuid4().hex[:10]}",
                user_id=user_id,
                live_location=True,
                emergency_communication=True,
                donation_requests=True,
                health_data_sharing=True,
                updated_at=now_str,
            )
            db.add(c)
            db.commit()
            db.refresh(c)
        return ConsentService._map_consent(c)

    @staticmethod
    def update_user_consent(
        db: Session,
        user_id: str,
        data: ConsentUpdateRequest,
        current_user: UserProfileSchema,
    ) -> ConsentResponse:
        c = db.query(Consent).filter(Consent.user_id == user_id).first()
        now_str = datetime.now(timezone.utc).isoformat()
        if not c:
            c = Consent(
                id=f"cns-{uuid.uuid4().hex[:10]}",
                user_id=user_id,
                live_location=data.liveLocation if data.liveLocation is not None else True,
                emergency_communication=data.emergencyCommunication if data.emergencyCommunication is not None else True,
                donation_requests=data.donationRequests if data.donationRequests is not None else True,
                health_data_sharing=data.healthDataSharing if data.healthDataSharing is not None else True,
                updated_at=now_str,
            )
            db.add(c)
        else:
            if data.liveLocation is not None:
                c.live_location = data.liveLocation
            if data.emergencyCommunication is not None:
                c.emergency_communication = data.emergencyCommunication
            if data.donationRequests is not None:
                c.donation_requests = data.donationRequests
            if data.healthDataSharing is not None:
                c.health_data_sharing = data.healthDataSharing
            c.updated_at = now_str

        audit = AuditLog(
            id=f"audit-{uuid.uuid4().hex[:10]}",
            timestamp=now_str,
            actor=current_user.name,
            actor_type="user",
            action="Updated user consent settings",
            resource="Consent Policy",
            resource_id=user_id,
            authorization="User Consent Authorization",
            status="success",
            module="system",
        )
        db.add(audit)
        db.commit()
        db.refresh(c)
        return ConsentService._map_consent(c)


consent_service = ConsentService()
