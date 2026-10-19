import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.interaction import DonorEmergencyInteraction
from app.models.emergency import Emergency, EmergencyEvent
from app.models.donor import Donor
from app.models.consent import Consent
from app.models.audit import AuditLog
from app.schemas.auth import UserProfileSchema
from app.schemas.interaction import (
    CandidateSelectionRequest,
    ContactAttemptRequest,
    ContactDeliveredRequest,
    ContactFailedRequest,
    ContactTimeoutRequest,
    InteractionCancellationRequest,
    DonorResponseRecordRequest,
    DonationCompletionRequest,
    DonorInteractionResponse,
    ContactStatus,
    ResponseStatus,
    AcceptanceStatus,
    CompletionStatus,
)


import threading
_selection_lock = threading.Lock()


class InteractionService:
    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def record_candidate_selection(
        db: Session,
        req: CandidateSelectionRequest,
        current_user: UserProfileSchema,
    ) -> DonorInteractionResponse:
        # 1. Verify Emergency exists
        emergency = db.query(Emergency).filter(Emergency.id == req.emergencyId).first()
        if not emergency:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Emergency '{req.emergencyId}' not found",
            )

        # 2. Verify Donor exists
        donor = db.query(Donor).filter(Donor.id == req.donorId).first()
        if not donor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Donor '{req.donorId}' not found",
            )

        # 3. Medical eligibility check
        if donor.eligibility == "ineligible":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Donor '{donor.id}' is medically ineligible ({donor.eligibility_reason or 'disqualified'})",
            )

        # 4. Thread-safe duplicate check and candidate registration
        with _selection_lock:
            existing = (
                db.query(DonorEmergencyInteraction)
                .filter(
                    DonorEmergencyInteraction.emergency_id == req.emergencyId,
                    DonorEmergencyInteraction.donor_id == req.donorId,
                    DonorEmergencyInteraction.completion_status == "pending",
                )
                .first()
            )
            if existing:
                return DonorInteractionResponse.model_validate(existing)

            now = datetime.now(timezone.utc)
            now_str = now.isoformat()
            time_of_day = now.hour + (now.minute / 60.0)
            day_of_week = now.weekday()  # 0=Monday, 6=Sunday

            distance = req.distanceKm if req.distanceKm is not None else donor.distance_km
            eta = req.etaMinutes if req.etaMinutes is not None else donor.eta_minutes

            interaction = DonorEmergencyInteraction(
                id=f"dint-{uuid.uuid4().hex[:12]}",
                emergency_id=req.emergencyId,
                donor_id=req.donorId,
                selected_at=now_str,
                # Snapshot features
                distance_km=distance,
                eta_minutes=eta,
                time_of_day_hours=round(time_of_day, 2),
                day_of_week=day_of_week,
                emergency_priority=emergency.priority,
                compatibility_match_type=req.compatibilityMatchType or "identical",
                donor_availability_at_selection=donor.status,
                donor_total_previous_donations=0,
                donor_days_since_last_donation=donor.last_donation_days,
                # States
                contact_status=ContactStatus.PENDING.value,
                response_status=ResponseStatus.PENDING.value,
                acceptance_status=AcceptanceStatus.PENDING.value,
                completion_status=CompletionStatus.PENDING.value,
                # Provenance
                outcome_source="system",
                data_provenance=req.dataProvenance.value,
                is_synthetic=req.isSynthetic,
                notes=req.notes,
                created_at=now_str,
                updated_at=now_str,
            )

            db.add(interaction)

            audit = AuditLog(
                id=f"audit-int-sel-{uuid.uuid4().hex[:10]}",
                timestamp=now_str,
                actor=current_user.name,
                actor_type="user",
                action=f"Candidate donor #{donor.id} selected for emergency #{emergency.id} (Snapshot recorded)",
                resource=f"Interaction #{interaction.id}",
                resource_id=interaction.id,
                authorization=f"Role: {current_user.role}",
                status="success",
                module="blood",
            )
            db.add(audit)
            db.commit()
            db.refresh(interaction)

            return DonorInteractionResponse.model_validate(interaction)

    @staticmethod
    def record_contact_attempt(
        db: Session,
        interaction_id: str,
        req: ContactAttemptRequest,
        current_user: UserProfileSchema,
    ) -> DonorInteractionResponse:
        interaction = db.query(DonorEmergencyInteraction).filter(DonorEmergencyInteraction.id == interaction_id).first()
        if not interaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interaction '{interaction_id}' not found",
            )

        # Verify donor emergency communication consent and synthetic safety guard
        donor = db.query(Donor).filter(Donor.id == interaction.donor_id).first()
        if not donor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Associated donor '{interaction.donor_id}' not found",
            )

        now_str = InteractionService._now_iso()

        # Strict safety guard: never send real emergency notifications to synthetic/test profiles
        if getattr(donor, "is_synthetic", False) or getattr(donor, "data_provenance", "production") != "production":
            audit = AuditLog(
                id=f"audit-synthetic-blocked-{uuid.uuid4().hex[:10]}",
                timestamp=now_str,
                actor=current_user.name,
                actor_type="user",
                action=f"Donor #{donor.id} contact attempt blocked: Synthetic benchmark profile cannot receive real emergency alerts",
                resource=f"Donor #{donor.id}",
                resource_id=donor.id,
                authorization=f"Role: {current_user.role}",
                status="failed",
                module="blood",
            )
            db.add(audit)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Donor #{donor.id} is a synthetic benchmark profile. Live notifications are strictly prohibited.",
            )

        # Verify donor emergency communication consent
        consent = None
        if donor.user_id:
            consent = db.query(Consent).filter(Consent.user_id == donor.user_id).first()

        has_consent = bool(consent and consent.emergency_communication)
        if not has_consent:
            audit = AuditLog(
                id=f"audit-consent-denied-{uuid.uuid4().hex[:10]}",
                timestamp=now_str,
                actor=current_user.name,
                actor_type="user",
                action=f"Donor #{donor.id} contact attempt blocked: Emergency communication consent not granted",
                resource=f"Donor #{donor.id}",
                resource_id=donor.id,
                authorization=f"Role: {current_user.role}",
                status="failed",
                module="blood",
            )
            db.add(audit)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Donor #{donor.id} has not granted emergency communication consent",
            )

        # Idempotency / State Transition Check
        if interaction.contact_status != ContactStatus.PENDING.value:
            if interaction.contact_status in [ContactStatus.ATTEMPTED.value, ContactStatus.DELIVERED.value]:
                return DonorInteractionResponse.model_validate(interaction)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot attempt contact from current contact status '{interaction.contact_status}'",
            )

        interaction.contact_status = ContactStatus.ATTEMPTED.value
        interaction.contact_channel = req.contactChannel.value
        interaction.contact_attempted_at = now_str
        interaction.outcome_source = req.outcomeSource.value
        if req.notes:
            interaction.notes = (interaction.notes or "") + f" | Contact attempt: {req.notes}"
        interaction.updated_at = now_str

        # Synchronize donor and emergency events
        if donor:
            donor.status = "contacted"
            donor.contacted_at = now_str

        evt = EmergencyEvent(
            id=f"evt-{uuid.uuid4().hex[:10]}",
            emergency_id=interaction.emergency_id,
            timestamp=now_str,
            actor=current_user.name,
            action=f"Contact attempt dispatched to Donor #{interaction.donor_id} via {req.contactChannel.value}",
            resource=f"Interaction #{interaction.id}",
            authorization=f"Role: {current_user.role}",
            status="success",
        )
        db.add(evt)

        audit = AuditLog(
            id=f"audit-int-att-{uuid.uuid4().hex[:10]}",
            timestamp=now_str,
            actor=current_user.name,
            actor_type="user",
            action=f"Contact attempt logged for Interaction #{interaction.id}",
            resource=f"Interaction #{interaction.id}",
            resource_id=interaction.id,
            authorization=f"Role: {current_user.role}",
            status="success",
            module="blood",
        )
        db.add(audit)

        db.commit()
        db.refresh(interaction)

        try:
            from app.realtime.manager import ws_manager
            from app.realtime.events import RealtimeEvent, RealtimeEventType
            ws_manager.broadcast_sync(
                RealtimeEvent(
                    type=RealtimeEventType.DONOR_CONTACTED.value,
                    payload={
                        "interactionId": interaction.id,
                        "donorId": interaction.donor_id,
                        "emergencyId": interaction.emergency_id,
                        "channel": req.contactChannel.value,
                    },
                )
            )
        except Exception:
            pass

        return DonorInteractionResponse.model_validate(interaction)

    @staticmethod
    def record_contact_delivery(
        db: Session,
        interaction_id: str,
        req: ContactDeliveredRequest,
        current_user: UserProfileSchema,
    ) -> DonorInteractionResponse:
        interaction = db.query(DonorEmergencyInteraction).filter(DonorEmergencyInteraction.id == interaction_id).first()
        if not interaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interaction '{interaction_id}' not found",
            )

        # Transition validation: must have been attempted
        if interaction.contact_status != ContactStatus.ATTEMPTED.value:
            if interaction.contact_status == ContactStatus.DELIVERED.value:
                return DonorInteractionResponse.model_validate(interaction)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot record delivery for unattempted contact (current: '{interaction.contact_status}')",
            )

        now_str = InteractionService._now_iso()
        interaction.contact_status = ContactStatus.DELIVERED.value
        interaction.contact_delivered_at = now_str
        interaction.outcome_source = req.outcomeSource.value
        interaction.updated_at = now_str

        db.commit()
        db.refresh(interaction)
        return DonorInteractionResponse.model_validate(interaction)

    @staticmethod
    def record_contact_failed(
        db: Session,
        interaction_id: str,
        req: ContactFailedRequest,
        current_user: UserProfileSchema,
    ) -> DonorInteractionResponse:
        interaction = db.query(DonorEmergencyInteraction).filter(DonorEmergencyInteraction.id == interaction_id).first()
        if not interaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interaction '{interaction_id}' not found",
            )

        if interaction.contact_status == ContactStatus.FAILED.value:
            return DonorInteractionResponse.model_validate(interaction)

        if interaction.contact_status not in [ContactStatus.PENDING.value, ContactStatus.ATTEMPTED.value]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot record contact failure from current status '{interaction.contact_status}'",
            )

        now_str = InteractionService._now_iso()
        interaction.contact_status = ContactStatus.FAILED.value
        interaction.outcome_source = req.outcomeSource.value
        interaction.notes = (interaction.notes or "") + f" | Contact failed: {req.failureReason}"
        interaction.updated_at = now_str

        audit = AuditLog(
            id=f"audit-int-fail-{uuid.uuid4().hex[:10]}",
            timestamp=now_str,
            actor=current_user.name,
            actor_type="user",
            action=f"Contact failure recorded for Interaction #{interaction.id}: {req.failureReason}",
            resource=f"Interaction #{interaction.id}",
            resource_id=interaction.id,
            authorization=f"Role: {current_user.role}",
            status="failed",
            module="blood",
        )
        db.add(audit)
        db.commit()
        db.refresh(interaction)
        return DonorInteractionResponse.model_validate(interaction)

    @staticmethod
    def record_donor_response(
        db: Session,
        interaction_id: str,
        req: DonorResponseRecordRequest,
        current_user: UserProfileSchema,
    ) -> DonorInteractionResponse:
        interaction = db.query(DonorEmergencyInteraction).filter(DonorEmergencyInteraction.id == interaction_id).first()
        if not interaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interaction '{interaction_id}' not found",
            )

        # If current user is a donor, ensure they are responding ONLY to their own interaction
        donor = db.query(Donor).filter(Donor.id == interaction.donor_id).first()
        if current_user.role == "donor":
            if not donor or donor.user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Donors can only submit responses for their own interaction requests",
                )

        # State transition validation: must be contacted before responding
        if interaction.contact_status not in [ContactStatus.ATTEMPTED.value, ContactStatus.DELIVERED.value]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot record response for unattempted interaction (contact_status='{interaction.contact_status}')",
            )

        if interaction.response_status != ResponseStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Response has already been recorded for this interaction (current: '{interaction.response_status}')",
            )

        now = datetime.now(timezone.utc)
        now_str = now.isoformat()

        latency_seconds = None
        if interaction.contact_attempted_at:
            try:
                attempted_dt = datetime.fromisoformat(interaction.contact_attempted_at)
                latency_seconds = max(0, int((now - attempted_dt).total_seconds()))
            except Exception:
                latency_seconds = None

        interaction.response_status = ResponseStatus.RESPONDED.value
        interaction.responded_at = now_str
        interaction.response_latency_seconds = latency_seconds
        interaction.outcome_source = req.outcomeSource.value
        interaction.updated_at = now_str

        if req.accepted:
            interaction.acceptance_status = AcceptanceStatus.ACCEPTED.value
            if donor:
                donor.status = "accepted"
                donor.responded_at = now_str
                if bool(getattr(req, "shareLocation", False)):
                    donor.location_consent_granted = True
        else:
            interaction.acceptance_status = AcceptanceStatus.DECLINED.value
            interaction.rejection_reason = req.rejectionReason
            if donor:
                donor.status = "declined"
                donor.responded_at = now_str

        audit = AuditLog(
            id=f"audit-int-resp-{uuid.uuid4().hex[:10]}",
            timestamp=now_str,
            actor=current_user.name,
            actor_type="user" if current_user.role != "donor" else "donor",
            action=f"Response logged for Interaction #{interaction.id}: accepted={req.accepted} (latency: {latency_seconds}s)",
            resource=f"Interaction #{interaction.id}",
            resource_id=interaction.id,
            authorization=f"Role: {current_user.role}",
            status="success",
            module="blood",
        )
        db.add(audit)

        db.commit()
        db.refresh(interaction)

        try:
            from app.realtime.manager import ws_manager
            from app.realtime.events import RealtimeEvent, RealtimeEventType
            evt_type = (
                RealtimeEventType.DONOR_ACCEPTED.value
                if req.accepted
                else RealtimeEventType.DONOR_DECLINED.value
            )
            ws_manager.broadcast_sync(
                RealtimeEvent(
                    type=evt_type,
                    payload={
                        "interactionId": interaction.id,
                        "donorId": interaction.donor_id,
                        "emergencyId": interaction.emergency_id,
                        "accepted": req.accepted,
                        "rejectionReason": req.rejectionReason if not req.accepted else None,
                    },
                )
            )
        except Exception:
            pass

        return DonorInteractionResponse.model_validate(interaction)

    @staticmethod
    def record_contact_timeout(
        db: Session,
        interaction_id: str,
        req: ContactTimeoutRequest,
        current_user: UserProfileSchema,
    ) -> DonorInteractionResponse:
        interaction = db.query(DonorEmergencyInteraction).filter(DonorEmergencyInteraction.id == interaction_id).first()
        if not interaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interaction '{interaction_id}' not found",
            )

        # Must have been attempted or delivered before timeout
        if interaction.contact_status not in [ContactStatus.ATTEMPTED.value, ContactStatus.DELIVERED.value]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot record timeout for uncontacted interaction (contact_status='{interaction.contact_status}')",
            )

        if interaction.response_status != ResponseStatus.PENDING.value:
            if interaction.response_status in [ResponseStatus.NO_RESPONSE.value, ResponseStatus.EXPIRED.value]:
                return DonorInteractionResponse.model_validate(interaction)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot time out an interaction that already has response status '{interaction.response_status}'",
            )

        now_str = InteractionService._now_iso()
        interaction.response_status = ResponseStatus.NO_RESPONSE.value
        interaction.acceptance_status = AcceptanceStatus.UNREACHABLE.value
        interaction.response_latency_seconds = None  # Preserves data integrity: latency is unobserved!
        interaction.outcome_source = req.outcomeSource.value
        if req.timeoutReason:
            interaction.notes = (interaction.notes or "") + f" | Timeout: {req.timeoutReason}"
        interaction.updated_at = now_str

        donor = db.query(Donor).filter(Donor.id == interaction.donor_id).first()
        if donor:
            donor.status = "no_response"

        audit = AuditLog(
            id=f"audit-int-tout-{uuid.uuid4().hex[:10]}",
            timestamp=now_str,
            actor=current_user.name,
            actor_type="user",
            action=f"Response timeout recorded for Interaction #{interaction.id} (unreachable)",
            resource=f"Interaction #{interaction.id}",
            resource_id=interaction.id,
            authorization=f"Role: {current_user.role}",
            status="success",
            module="blood",
        )
        db.add(audit)
        db.commit()
        db.refresh(interaction)
        return DonorInteractionResponse.model_validate(interaction)

    @staticmethod
    def record_donation_completion(
        db: Session,
        interaction_id: str,
        req: DonationCompletionRequest,
        current_user: UserProfileSchema,
    ) -> DonorInteractionResponse:
        interaction = db.query(DonorEmergencyInteraction).filter(DonorEmergencyInteraction.id == interaction_id).first()
        if not interaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interaction '{interaction_id}' not found",
            )

        # Transition validation: must have been accepted
        if interaction.acceptance_status != AcceptanceStatus.ACCEPTED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot complete donation for non-accepted interaction (acceptance_status='{interaction.acceptance_status}')",
            )

        if interaction.completion_status != CompletionStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Completion outcome already recorded for this interaction (current: '{interaction.completion_status}')",
            )

        now_str = InteractionService._now_iso()
        interaction.completion_status = req.completionStatus.value
        interaction.completed_at = now_str
        interaction.units_donated = req.unitsDonated if req.completionStatus == CompletionStatus.COMPLETED else 0
        interaction.outcome_source = req.outcomeSource.value
        interaction.updated_at = now_str

        audit = AuditLog(
            id=f"audit-int-comp-{uuid.uuid4().hex[:10]}",
            timestamp=now_str,
            actor=current_user.name,
            actor_type="user",
            action=f"Donation completion outcome recorded for Interaction #{interaction.id}: status={req.completionStatus.value}",
            resource=f"Interaction #{interaction.id}",
            resource_id=interaction.id,
            authorization=f"Role: {current_user.role}",
            status="success",
            module="blood",
        )
        db.add(audit)

        db.commit()
        db.refresh(interaction)
        return DonorInteractionResponse.model_validate(interaction)

    @staticmethod
    def record_interaction_cancellation(
        db: Session,
        interaction_id: str,
        req: InteractionCancellationRequest,
        current_user: UserProfileSchema,
    ) -> DonorInteractionResponse:
        interaction = db.query(DonorEmergencyInteraction).filter(DonorEmergencyInteraction.id == interaction_id).first()
        if not interaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interaction '{interaction_id}' not found",
            )

        if interaction.completion_status == CompletionStatus.CANCELED.value:
            return DonorInteractionResponse.model_validate(interaction)

        if interaction.completion_status == CompletionStatus.COMPLETED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot cancel an interaction whose donation has already been completed",
            )

        now_str = InteractionService._now_iso()
        interaction.completion_status = CompletionStatus.CANCELED.value
        interaction.outcome_source = req.outcomeSource.value
        if req.cancellationReason:
            interaction.notes = (interaction.notes or "") + f" | Cancelled: {req.cancellationReason}"
        interaction.updated_at = now_str

        audit = AuditLog(
            id=f"audit-int-cnc-{uuid.uuid4().hex[:10]}",
            timestamp=now_str,
            actor=current_user.name,
            actor_type="user",
            action=f"Cancellation recorded for Interaction #{interaction.id}: {req.cancellationReason}",
            resource=f"Interaction #{interaction.id}",
            resource_id=interaction.id,
            authorization=f"Role: {current_user.role}",
            status="success",
            module="blood",
        )
        db.add(audit)
        db.commit()
        db.refresh(interaction)
        return DonorInteractionResponse.model_validate(interaction)

    @staticmethod
    def get_interaction_by_id(
        db: Session,
        interaction_id: str,
        current_user: UserProfileSchema,
    ) -> DonorInteractionResponse:
        interaction = db.query(DonorEmergencyInteraction).filter(DonorEmergencyInteraction.id == interaction_id).first()
        if not interaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interaction '{interaction_id}' not found",
            )

        # Donor privacy boundary: Donors can only view their own interactions
        if current_user.role == "donor":
            donor = db.query(Donor).filter(Donor.id == interaction.donor_id).first()
            if not donor or donor.user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Donors can only inspect their own interaction records",
                )

        return DonorInteractionResponse.model_validate(interaction)

    @staticmethod
    def get_interaction_history(
        db: Session,
        current_user: UserProfileSchema,
        emergency_id: Optional[str] = None,
        donor_id: Optional[str] = None,
        is_synthetic: Optional[bool] = None,
        data_provenance: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[DonorInteractionResponse], int]:
        query = db.query(DonorEmergencyInteraction)

        # Donor privacy boundary
        if current_user.role == "donor":
            user_donor = db.query(Donor).filter(Donor.user_id == current_user.id).first()
            if not user_donor:
                return [], 0
            query = query.filter(DonorEmergencyInteraction.donor_id == user_donor.id)
        else:
            if donor_id:
                query = query.filter(DonorEmergencyInteraction.donor_id == donor_id)

        if emergency_id:
            query = query.filter(DonorEmergencyInteraction.emergency_id == emergency_id)
        if is_synthetic is not None:
            query = query.filter(DonorEmergencyInteraction.is_synthetic == is_synthetic)
        if data_provenance:
            query = query.filter(DonorEmergencyInteraction.data_provenance == data_provenance)

        total = query.count()
        records = (
            query.order_by(desc(DonorEmergencyInteraction.selected_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [DonorInteractionResponse.model_validate(r) for r in records], total


interaction_service = InteractionService()
