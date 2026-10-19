import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.donor import Donor
from app.models.consent import Consent
from app.models.emergency import Emergency, EmergencyEvent
from app.models.hospital import Hospital
from app.models.audit import AuditLog
from app.models.interaction import DonorEmergencyInteraction
from app.services.matching_engine import baseline_matching_engine, CandidateEvaluation
from app.schemas.donor import (
    DonorResponse,
    Coordinates,
    RankedDonorsResponse,
    DonorSearchConfig,
    DonorAvailabilityRequest,
    DonorConsentResponse,
    DonorConsentUpdateRequest,
)
from app.schemas.emergency import EmergencyResponse, BloodEmergencyRequest
from app.schemas.auth import UserProfileSchema
from app.services.emergency_service import EmergencyService
from app.simulation.mock_notifications import mock_notification_provider


class DonorService:
    @staticmethod
    def _map_donor_to_response(d: Donor, mask_coordinates: bool = False) -> DonorResponse:
        coords = None
        if d.lat is not None and d.lng is not None:
            if not mask_coordinates or d.location_consent_granted:
                coords = Coordinates(lat=d.lat, lng=d.lng)

        return DonorResponse(
            id=d.id,
            bloodGroup=d.blood_group,
            distanceKm=d.distance_km,
            etaMinutes=d.eta_minutes,
            eligibility=d.eligibility,
            eligibilityReason=d.eligibility_reason,
            responseProbability=d.response_probability,
            reliabilityScore=d.reliability_score,
            reachabilityScore=d.reachability_score,
            aiRank=d.ai_rank,
            status=d.status,
            locationConsentGranted=d.location_consent_granted,
            lastDonationDays=d.last_donation_days,
            historicalAcceptanceRate=d.historical_acceptance_rate,
            contactedAt=d.contacted_at,
            respondedAt=d.responded_at,
            coordinates=coords,
        )

    @staticmethod
    def get_all(db: Session, current_user: Optional[UserProfileSchema] = None) -> List[DonorResponse]:
        donors = db.query(Donor).order_by(Donor.ai_rank.asc()).all()
        mask = current_user is None or current_user.role not in ["doctor", "hospital_staff", "admin"]
        return [DonorService._map_donor_to_response(d, mask_coordinates=mask) for d in donors]

    @staticmethod
    def get_by_id(db: Session, donor_id: str, current_user: Optional[UserProfileSchema] = None) -> DonorResponse:
        donor = db.query(Donor).filter(Donor.id == donor_id).first()
        if not donor:
            raise HTTPException(status_code=404, detail="Donor not found")
        mask = current_user is None or current_user.role not in ["doctor", "hospital_staff", "admin"]
        return DonorService._map_donor_to_response(donor, mask_coordinates=mask)

    @staticmethod
    def get_ranked_donors(
        db: Session,
        emergency_id: str,
        current_user: Optional[UserProfileSchema] = None,
    ) -> RankedDonorsResponse:
        emergency = db.query(Emergency).filter(Emergency.id == emergency_id).first()

        # 1. Retrieve hospital coordinates through emergency -> hospital relationship
        hospital_lat: Optional[float] = None
        hospital_lng: Optional[float] = None
        if emergency and emergency.hospital_id:
            hospital = db.query(Hospital).filter(Hospital.id == emergency.hospital_id).first()
            if hospital:
                hospital_lat = hospital.lat
                hospital_lng = hospital.lng

        # 2. Determine recipient blood group from emergency
        recipient_group = emergency.blood_group if (emergency and emergency.blood_group) else "O-"

        # 3. Retrieve all candidate donors
        all_donors = db.query(Donor).all()

        # 4. Evaluate candidates through deterministic baseline matching engine
        ranked_candidates, excluded_candidates = baseline_matching_engine.evaluate_candidates(
            donors=all_donors,
            recipient_blood_group=recipient_group,
            hospital_lat=hospital_lat,
            hospital_lng=hospital_lng,
        )

        mask_coords = current_user is None or current_user.role not in ["doctor", "hospital_staff", "admin"]

        # 5. Handle empty candidate pool
        if not ranked_candidates:
            search_config = DonorSearchConfig(
                initialRadiusKm=2.0,
                currentRadiusKm=5.0,
                maxRadiusKm=15.0,
                expansionCount=2,
                expansionReason=f"No eligible, compatible donors found within current radius for blood group {recipient_group}. Expanding search radius.",
            )
            recommendation = (
                f"No eligible compatible donors found for recipient blood group {recipient_group}. "
                f"All {len(excluded_candidates)} evaluated donors were excluded due to compatibility mismatch, medical deferral, or unavailability."
            )
            return RankedDonorsResponse(
                donors=[],
                searchConfig=search_config,
                aiRecommendation=recommendation,
            )

        # 6. Map ranked candidates to frontend-compatible DonorResponse schema
        donor_responses: List[DonorResponse] = []
        for cand in ranked_candidates:
            d = cand.donor
            coords = None
            if cand.has_valid_coordinates and d.lat is not None and d.lng is not None:
                if not mask_coords or d.location_consent_granted:
                    coords = Coordinates(lat=d.lat, lng=d.lng)

            calc_dist = cand.distance_km if cand.distance_km is not None else 0.0
            calc_eta = cand.eta_minutes if cand.eta_minutes is not None else 10
            hist_rate = int(round(cand.history_score)) if cand.has_observed_history else 0

            donor_responses.append(
                DonorResponse(
                    id=d.id,
                    bloodGroup=d.blood_group,
                    distanceKm=calc_dist,
                    etaMinutes=calc_eta,
                    eligibility=d.eligibility,
                    eligibilityReason=d.eligibility_reason,
                    responseProbability=cand.total_score,
                    reliabilityScore=int(round(cand.availability_score * 0.6 + cand.history_score * 0.4)),
                    reachabilityScore=int(round(cand.proximity_score)),
                    aiRank=cand.rank,
                    status=d.status,
                    locationConsentGranted=d.location_consent_granted,
                    lastDonationDays=d.last_donation_days,
                    historicalAcceptanceRate=hist_rate,
                    contactedAt=d.contacted_at,
                    respondedAt=d.responded_at,
                    coordinates=coords,
                )
            )

        top_cand = ranked_candidates[0]
        search_config = DonorSearchConfig(
            initialRadiusKm=2.0,
            currentRadiusKm=5.0,
            maxRadiusKm=15.0,
            expansionCount=1,
            expansionReason="Candidates matched and ranked via deterministic clinical baseline matching engine.",
        )
        recommendation = (
            f"Deterministic heuristic baseline: Candidate #{top_cand.donor.id} ranked #1. {top_cand.explanation}"
        )

        return RankedDonorsResponse(
            donors=donor_responses,
            searchConfig=search_config,
            aiRecommendation=recommendation,
        )

    @staticmethod
    def contact_donor(db: Session, donor_id: str, emergency_id: str, current_user: UserProfileSchema) -> dict:
        # 1. Verify donor exists
        donor = db.query(Donor).filter(Donor.id == donor_id).first()
        if not donor:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donor not found")

        now_str = datetime.now(timezone.utc).isoformat()

        # Strict safety guard: never send real emergency notifications to synthetic/test profiles
        if getattr(donor, "is_synthetic", False) or getattr(donor, "data_provenance", "production") != "production":
            audit = AuditLog(
                id=f"audit-synthetic-blocked-{uuid.uuid4().hex[:10]}",
                timestamp=now_str,
                actor=current_user.name,
                actor_type="user",
                action=f"Donor #{donor.id} contact blocked: Synthetic benchmark profile cannot receive real emergency alerts",
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

        # 2. Verify emergency communication consent
        consent = None
        if donor.user_id:
            consent = db.query(Consent).filter(Consent.user_id == donor.user_id).first()

        has_consent = bool(consent and consent.emergency_communication)
        if not has_consent:
            # Record consent denial decision in audit log
            audit = AuditLog(
                id=f"audit-consent-denied-{uuid.uuid4().hex[:10]}",
                timestamp=now_str,
                actor=current_user.name,
                actor_type="user",
                action=f"Donor #{donor.id} contact blocked: Emergency communication consent not granted",
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

        # 3. Verify appropriate donor status and affirmative clinical eligibility
        if (donor.eligibility or "").lower() != "eligible" or donor.status in ["declined", "unavailable"]:
            audit = AuditLog(
                id=f"audit-status-ineligible-{uuid.uuid4().hex[:10]}",
                timestamp=now_str,
                actor=current_user.name,
                actor_type="user",
                action=f"Donor #{donor.id} contact blocked: Inappropriate status ({donor.status}) or eligibility ({donor.eligibility})",
                resource=f"Donor #{donor.id}",
                resource_id=donor.id,
                authorization=f"Role: {current_user.role}",
                status="failed",
                module="blood",
            )
            db.add(audit)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Donor #{donor.id} status is inappropriate for contact: status={donor.status}, eligibility={donor.eligibility}",
            )

        prior_status = donor.status

        # 4. Update status and record decision in audit log
        donor.status = "contacted"
        donor.contacted_at = now_str

        # Synchronize interaction ledger
        active_interaction = (
            db.query(DonorEmergencyInteraction)
            .filter(
                DonorEmergencyInteraction.emergency_id == emergency_id,
                DonorEmergencyInteraction.donor_id == donor_id,
                DonorEmergencyInteraction.completion_status == "pending",
            )
            .first()
        )
        if not active_interaction:
            emerg = db.query(Emergency).filter(Emergency.id == emergency_id).first()
            now_dt = datetime.now(timezone.utc)
            active_interaction = DonorEmergencyInteraction(
                id=f"dint-{uuid.uuid4().hex[:12]}",
                emergency_id=emergency_id,
                donor_id=donor_id,
                selected_at=now_str,
                distance_km=donor.distance_km,
                eta_minutes=donor.eta_minutes,
                time_of_day_hours=round(now_dt.hour + (now_dt.minute / 60.0), 2),
                day_of_week=now_dt.weekday(),
                emergency_priority=emerg.priority if emerg else "critical",
                compatibility_match_type="identical",
                donor_availability_at_selection=prior_status,
                donor_total_previous_donations=0,
                donor_days_since_last_donation=donor.last_donation_days,
                contact_status="attempted",
                contact_channel="sms",
                contact_attempted_at=now_str,
                response_status="pending",
                acceptance_status="pending",
                completion_status="pending",
                outcome_source="dispatcher_portal",
                data_provenance="production",
                is_synthetic=False,
                created_at=now_str,
                updated_at=now_str,
            )
            db.add(active_interaction)
        else:
            if active_interaction.contact_status == "pending":
                active_interaction.contact_status = "attempted"
                active_interaction.contact_channel = "sms"
                active_interaction.contact_attempted_at = now_str
                active_interaction.updated_at = now_str

        # Record simulated notification dispatch (asserts carrier isolation)
        mock_notification_provider.dispatch(
            recipient=f"Donor #{donor.id} ({donor.blood_group})",
            message=f"LifeLink Urgent Blood Emergency: Compatible donor needed for emergency {emergency_id}",
            channel="sms",
            metadata={"emergency_id": emergency_id, "donor_id": donor_id, "actor": current_user.name},
        )

        # Add event to emergency
        evt = EmergencyEvent(
            id=f"evt-{uuid.uuid4().hex[:10]}",
            emergency_id=emergency_id,
            timestamp=now_str,
            actor=current_user.name,
            action=f"Donor #{donor.id} ({donor.blood_group}) contacted (mock notification; Twilio unavailable/not configured)",
            resource=f"Donor #{donor.id}",
            authorization=f"Role: {current_user.role}",
            status="success",
        )
        db.add(evt)

        # Record consent-approved decision in audit log
        audit = AuditLog(
            id=f"audit-{uuid.uuid4().hex[:10]}",
            timestamp=now_str,
            actor=current_user.name,
            actor_type="user",
            action=f"Donor #{donor.id} contact approved: Verified emergency communication consent",
            resource=f"Donor #{donor.id}",
            resource_id=donor.id,
            authorization=f"Role: {current_user.role}",
            status="success",
            module="blood",
        )
        db.add(audit)

        db.commit()
        return {"status": "contacted", "donorId": donor_id, "contactedAt": now_str}

    @staticmethod
    def record_donor_response(
        db: Session,
        donor_id: str,
        status_choice: str,
        share_location: bool = False,
        current_user: Optional[UserProfileSchema] = None,
    ) -> dict:
        donor = db.query(Donor).filter(Donor.id == donor_id).first()
        if not donor:
            raise HTTPException(status_code=404, detail="Donor not found")

        # Authorization: If logged in as donor, ensure they are responding ONLY to their own donor profile
        if current_user and current_user.role == "donor":
            if not donor.user_id or donor.user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Donors can only submit responses for their own profile",
                )

        now_str = datetime.now(timezone.utc).isoformat()

        # Synchronize active interaction record if present
        active_int = (
            db.query(DonorEmergencyInteraction)
            .filter(
                DonorEmergencyInteraction.donor_id == donor_id,
                DonorEmergencyInteraction.response_status == "pending",
            )
            .order_by(DonorEmergencyInteraction.selected_at.desc())
            .first()
        )

        # Idempotency / repeated submission check
        if not active_int and donor.status in ["accepted", "declined"] and donor.status == status_choice:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Response has already been recorded for this donor (current status: '{donor.status}')",
            )

        donor.status = status_choice
        donor.responded_at = now_str
        if share_location:
            donor.location_consent_granted = True

        if active_int:
            active_int.updated_at = now_str
            if status_choice in ["accepted", "en_route", "declined"]:
                latency_s = None
                if active_int.contact_attempted_at:
                    try:
                        att_dt = datetime.fromisoformat(active_int.contact_attempted_at)
                        latency_s = max(0, int((datetime.now(timezone.utc) - att_dt).total_seconds()))
                    except Exception:
                        latency_s = None
                active_int.response_latency_seconds = latency_s
                active_int.responded_at = now_str
                active_int.response_status = "responded"
                if status_choice in ["accepted", "en_route"]:
                    active_int.acceptance_status = "accepted"
                else:
                    active_int.acceptance_status = "declined"
            elif status_choice in ["no_response", "unavailable"]:
                active_int.response_latency_seconds = None
                active_int.responded_at = None
                active_int.response_status = "no_response"
                active_int.acceptance_status = "unreachable"

        # Record audit log entry
        actor_name = current_user.name if current_user else f"Donor #{donor.id}"
        actor_role = current_user.role if current_user else "donor"
        audit = AuditLog(
            id=f"audit-dnr-resp-{uuid.uuid4().hex[:10]}",
            timestamp=now_str,
            actor=actor_name,
            actor_type="donor" if actor_role == "donor" else "user",
            action=f"Donor #{donor.id} response recorded: status={status_choice}, location_shared={bool(share_location)}",
            resource=f"Donor #{donor.id}",
            resource_id=donor.id,
            authorization=f"Role: {actor_role}",
            status="success",
            module="blood",
        )
        db.add(audit)

        db.commit()

        # Real-time WebSocket event broadcast
        try:
            from app.realtime.manager import ws_manager
            from app.realtime.events import RealtimeEvent, RealtimeEventType
            ws_manager.broadcast_sync(
                RealtimeEvent(
                    type=RealtimeEventType.DONOR_ACCEPTED.value if status_choice in ["accepted", "en_route"] else RealtimeEventType.DONOR_DECLINED.value,
                    payload={
                        "donorId": donor.id,
                        "status": status_choice,
                        "locationConsentGranted": donor.location_consent_granted,
                    },
                )
            )
        except Exception:
            pass

        return {
            "status": donor.status,
            "donorId": donor.id,
            "respondedAt": donor.responded_at,
            "locationConsentGranted": donor.location_consent_granted,
        }

    @staticmethod
    def get_donor_me(db: Session, current_user: UserProfileSchema) -> DonorResponse:
        donor = db.query(Donor).filter(Donor.user_id == current_user.id).first()
        if not donor:
            raise HTTPException(status_code=404, detail="Donor profile not found for current user")
        return DonorService._map_donor_to_response(donor, mask_coordinates=False)

    @staticmethod
    def get_donor_consent(db: Session, current_user: UserProfileSchema) -> DonorConsentResponse:
        consent = db.query(Consent).filter(Consent.user_id == current_user.id).first()
        if not consent:
            return DonorConsentResponse(
                liveLocation=True,
                emergencyCommunication=True,
                donationRequests=True,
                healthDataSharing=True,
                updatedAt=datetime.now(timezone.utc).isoformat(),
            )
        return DonorConsentResponse(
            liveLocation=consent.live_location,
            emergencyCommunication=consent.emergency_communication,
            donationRequests=consent.donation_requests,
            healthDataSharing=consent.health_data_sharing,
            updatedAt=consent.updated_at,
        )

    @staticmethod
    def update_donor_consent(db: Session, data: DonorConsentUpdateRequest, current_user: UserProfileSchema) -> DonorConsentResponse:
        consent = db.query(Consent).filter(Consent.user_id == current_user.id).first()
        now_str = datetime.now(timezone.utc).isoformat()
        if not consent:
            consent = Consent(
                id=f"cns-{int(datetime.now(timezone.utc).timestamp())}",
                user_id=current_user.id,
                live_location=data.liveLocation if data.liveLocation is not None else True,
                emergency_communication=data.emergencyCommunication if data.emergencyCommunication is not None else True,
                donation_requests=data.donationRequests if data.donationRequests is not None else True,
                health_data_sharing=data.healthDataSharing if data.healthDataSharing is not None else True,
                updated_at=now_str,
            )
            db.add(consent)
        else:
            if data.liveLocation is not None:
                consent.live_location = data.liveLocation
            if data.emergencyCommunication is not None:
                consent.emergency_communication = data.emergencyCommunication
            if data.donationRequests is not None:
                consent.donation_requests = data.donationRequests
            if data.healthDataSharing is not None:
                consent.health_data_sharing = data.healthDataSharing
            consent.updated_at = now_str

        # Audit consent update
        audit = AuditLog(
            id=f"audit-{int(datetime.now(timezone.utc).timestamp() * 1000) % 100000}",
            timestamp=now_str,
            actor=current_user.name,
            actor_type="donor",
            action="Updated privacy and data sharing consent preferences",
            resource="Donor Consent Center",
            resource_id=current_user.id,
            authorization="Self-Managed Consent",
            status="success",
            module="system",
        )
        db.add(audit)
        db.commit()
        db.refresh(consent)

        return DonorConsentResponse(
            liveLocation=consent.live_location,
            emergencyCommunication=consent.emergency_communication,
            donationRequests=consent.donation_requests,
            healthDataSharing=consent.health_data_sharing,
            updatedAt=consent.updated_at,
        )


donor_service = DonorService()
