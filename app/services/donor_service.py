import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.models.donor import Donor
from app.models.consent import Consent
from app.models.emergency import Emergency, EmergencyEvent
from app.models.hospital import Hospital
from app.models.audit import AuditLog
from app.models.interaction import DonorEmergencyInteraction
from app.services.matching_engine import baseline_matching_engine, CandidateEvaluation, get_compatible_donor_blood_groups
from app.schemas.donor import (
    DonorResponse,
    Coordinates,
    RankedDonorsResponse,
    DonorSearchConfig,
    DonorAvailabilityRequest,
    DonorConsentResponse,
    DonorConsentUpdateRequest,
    AcceptedDonorRankingEntry,
    EmergencyAcceptedDonorsRankingResponse,
    ContactedDonorSummary,
    DonorBatchDispatchResponse,
    DonorWorkflowStatusResponse,
)
from app.schemas.emergency import EmergencyResponse, BloodEmergencyRequest
from app.schemas.auth import UserProfileSchema
from app.services.emergency_service import EmergencyService
from app.simulation.mock_notifications import mock_notification_provider
from app.geo.service import geospatial_service, validate_coordinates, calculate_haversine_distance
from app.core.logging import logger
from app.core.config import settings


class DonorService:
    @staticmethod
    def _map_donor_to_response(
        d: Donor, mask_coordinates: bool = False, is_self: bool = False
    ) -> DonorResponse:
        coords = None
        if d.lat is not None and d.lng is not None:
            if is_self or (not mask_coordinates and d.location_consent_granted):
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
            name=getattr(d, "name", None),
            city=getattr(d, "city", None),
            district=getattr(d, "district", None),
            pincode=getattr(d, "pincode", None),
        )

    @staticmethod
    def get_all(
        db: Session,
        blood_group: Optional[str] = None,
        status: Optional[str] = None,
        eligibility: Optional[str] = None,
        city: Optional[str] = None,
        district: Optional[str] = None,
        max_distance_km: Optional[float] = None,
        skip: int = 0,
        limit: int = 50,
        current_user: Optional[UserProfileSchema] = None,
    ) -> List[DonorResponse]:
        query = db.query(Donor)
        if blood_group:
            query = query.filter(Donor.blood_group == blood_group.strip().upper())
        if status:
            query = query.filter(Donor.status == status.strip().lower())
        if eligibility:
            query = query.filter(Donor.eligibility == eligibility.strip().lower())
        if city:
            query = query.filter(Donor.city.ilike(f"%{city.strip()}%"))
        if district:
            query = query.filter(Donor.district.ilike(f"%{district.strip()}%"))
        if max_distance_km is not None:
            query = query.filter(Donor.distance_km <= max_distance_km)

        donors = query.order_by(Donor.ai_rank.asc()).offset(max(0, skip)).limit(min(max(1, limit), 100)).all()
        mask = current_user is None or current_user.role not in ["doctor", "hospital_staff", "admin"]
        return [
            DonorService._map_donor_to_response(
                d,
                mask_coordinates=mask,
                is_self=bool(current_user and d.user_id and current_user.id == d.user_id),
            )
            for d in donors
        ]

    @staticmethod
    def get_by_id(db: Session, donor_id: str, current_user: Optional[UserProfileSchema] = None) -> DonorResponse:
        donor = db.query(Donor).filter(Donor.id == donor_id).first()
        if not donor:
            raise HTTPException(status_code=404, detail="Donor not found")
        is_self = bool(current_user and donor.user_id and current_user.id == donor.user_id)
        mask = current_user is None or current_user.role not in ["doctor", "hospital_staff", "admin"]
        return DonorService._map_donor_to_response(donor, mask_coordinates=mask, is_self=is_self)

    @staticmethod
    def get_ranked_donors(
        db: Session,
        emergency_id: str,
        current_user: Optional[UserProfileSchema] = None,
        min_candidates: Optional[int] = None,
        radius_tiers: Optional[List[float]] = None,
        demo_mode: bool = False,
    ) -> RankedDonorsResponse:
        # 1. Retrieve and validate emergency
        emergency = db.query(Emergency).filter(Emergency.id == emergency_id).first()
        if not emergency:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Emergency '{emergency_id}' not found",
            )

        # 2. Retrieve patient emergency coordinates
        # SAFETY RULE: Use patient emergency coordinates. Never substitute hospital coordinates when missing/invalid.
        raw_lat = getattr(emergency, "location_lat", None)
        raw_lng = getattr(emergency, "location_lng", None)
        has_valid_emergency_coords = False
        emergency_lat: Optional[float] = None
        emergency_lng: Optional[float] = None

        if raw_lat is not None and raw_lng is not None:
            try:
                validate_coordinates(float(raw_lat), float(raw_lng))
                emergency_lat = float(raw_lat)
                emergency_lng = float(raw_lng)
                has_valid_emergency_coords = True
            except (ValueError, TypeError):
                has_valid_emergency_coords = False

        # 3. Determine recipient blood group from emergency
        # CLINICAL SAFETY: If recipient blood group is unconfirmed/missing, emergency uncrossmatched
        # universal O- cellular protocol is applied as an emergency contingency pending laboratory testing.
        is_unknown_blood_group = not bool(emergency.blood_group and emergency.blood_group.strip())
        recipient_group = emergency.blood_group.strip().upper() if not is_unknown_blood_group else "O-"

        # 4. Retrieve candidate donors
        # PRODUCTION SAFETY: Production emergency ranking strictly excludes synthetic or test profiles.
        # Explicit demo emergencies (e.g., emg-demo-*) and requests with demo_mode=True include demo candidates.
        is_demo_emergency = bool(emergency.id and (emergency.id.lower().startswith("emg-demo") or emergency.id.lower().startswith("demo-")))
        allow_synthetic = demo_mode or is_demo_emergency

        query = db.query(Donor)
        if not allow_synthetic:
            query = query.filter(Donor.is_synthetic == False, Donor.data_provenance == "production")
        all_donors = query.all()


        # Configurable expansion parameters
        effective_min = (
            min_candidates
            if min_candidates is not None and min_candidates > 0
            else settings.DONOR_SEARCH_MIN_CANDIDATES
        )
        tiers = radius_tiers if radius_tiers else settings.DONOR_SEARCH_EXPANSION_TIERS
        tiers = sorted(list(set(tiers)))
        initial_radius = tiers[0] if tiers else 2.0
        max_radius = tiers[-1] if tiers else 20.0

        mask_coords = current_user is None or current_user.role not in ["doctor", "hospital_staff", "admin"]

        # 5. Case A: Emergency coordinates are missing or invalid
        # Do not substitute hospital coordinates. Return clear location-unavailable result without distance fabrication.
        if not has_valid_emergency_coords:
            ranked_candidates, excluded_candidates = baseline_matching_engine.evaluate_candidates(
                donors=all_donors,
                recipient_blood_group=recipient_group,
                hospital_lat=None,
                hospital_lng=None,
            )
            unlocalized_responses: List[DonorResponse] = []
            for idx, cand in enumerate(ranked_candidates, start=1):
                d = cand.donor
                coords = None
                if cand.has_valid_coordinates and d.lat is not None and d.lng is not None:
                    if not mask_coords and d.location_consent_granted:
                        coords = Coordinates(lat=d.lat, lng=d.lng)
                hist_rate = int(round(cand.history_score)) if cand.has_observed_history else 0
                unlocalized_responses.append(
                    DonorResponse(
                        id=d.id,
                        bloodGroup=d.blood_group,
                        distanceKm=None,
                        straightLineDistanceKm=None,
                        roadDistanceKm=None,
                        etaMinutes=None,
                        distanceSource="unavailable_missing_emergency_coordinates",
                        etaSource="unavailable_missing_emergency_coordinates",
                        isLiveEstimate=False,
                        eligibility=d.eligibility,
                        eligibilityReason=d.eligibility_reason,
                        responseProbability=cand.total_score,
                        reliabilityScore=int(round(cand.availability_score * 0.6 + cand.history_score * 0.4)),
                        reachabilityScore=int(round(cand.proximity_score)),
                        aiRank=idx,
                        status=d.status,
                        locationConsentGranted=d.location_consent_granted,
                        lastDonationDays=d.last_donation_days,
                        historicalAcceptanceRate=hist_rate,
                        contactedAt=d.contacted_at,
                        respondedAt=d.responded_at,
                        coordinates=coords,
                    )
                )

            search_config = DonorSearchConfig(
                initialRadiusKm=initial_radius,
                currentRadiusKm=initial_radius,
                maxRadiusKm=max_radius,
                expansionCount=0,
                expansionReason="Patient emergency coordinates are missing or invalid; location-based radius search and road routing unavailable.",
            )
            recommendation = (
                f"Patient emergency coordinates unavailable. Location-based road distance and driving ETA cannot be calculated. "
                f"Evaluated {len(ranked_candidates)} clinically compatible donor(s) without geographic proximity ranking."
            )
            return RankedDonorsResponse(
                donors=unlocalized_responses,
                searchConfig=search_config,
                aiRecommendation=recommendation,
                unlocalizedDonors=[],
            )

        # 6. Case B: Valid Emergency Origin Coordinates
        origin = (emergency_lat, emergency_lng)

        # Evaluate clinical compatibility and straight-line Haversine proximity from emergency origin
        ranked_candidates, excluded_candidates = baseline_matching_engine.evaluate_candidates(
            donors=all_donors,
            recipient_blood_group=recipient_group,
            hospital_lat=emergency_lat,
            hospital_lng=emergency_lng,
        )

        localized_candidates = [
            c for c in ranked_candidates if c.has_valid_coordinates and c.distance_km is not None
        ]
        unlocalized_candidates = [
            c for c in ranked_candidates if not c.has_valid_coordinates or c.distance_km is None
        ]

        # Progressive Multi-Tier Radius Expansion across [2.0, 5.0, 10.0, 20.0]
        current_radius = initial_radius
        expansion_count = 0
        matched_candidates: List[CandidateEvaluation] = []
        expansion_reason: str = ""

        for tier_idx, radius in enumerate(tiers):
            current_radius = radius
            expansion_count = tier_idx
            candidates_in_radius = [
                c for c in localized_candidates if c.distance_km <= radius
            ]
            if len(candidates_in_radius) >= effective_min:
                matched_candidates = candidates_in_radius
                if tier_idx == 0:
                    expansion_reason = (
                        f"Target candidate threshold met ({len(candidates_in_radius)} donor(s) >= {effective_min}) "
                        f"within initial {radius:.1f}km radius. No expansion required."
                    )
                else:
                    prev_tier = tiers[tier_idx - 1]
                    expansion_reason = (
                        f"Search radius progressively expanded from {prev_tier:.1f}km to {radius:.1f}km "
                        f"(expansion step {tier_idx}) because previous tier yielded fewer than target {effective_min} candidate(s). "
                        f"Found {len(candidates_in_radius)} eligible compatible donor(s)."
                    )
                break
        else:
            # Maximum radius tier reached
            current_radius = max_radius
            expansion_count = len(tiers) - 1
            candidates_in_radius = [
                c for c in localized_candidates if c.distance_km <= max_radius
            ]
            matched_candidates = candidates_in_radius
            if len(matched_candidates) > 0:
                expansion_reason = (
                    f"Maximum search radius of {max_radius:.1f}km reached. "
                    f"Found {len(matched_candidates)} donor(s) within {max_radius:.1f}km (target threshold: {effective_min})."
                )
            else:
                expansion_reason = (
                    f"No eligible compatible donors found within maximum {max_radius:.1f}km search radius "
                    f"for blood group {recipient_group}."
                )

        # 7. Google Maps Road Distance and Driving ETA for matched candidates within reached radius
        geo_results: List[Dict[str, Any]] = []
        if matched_candidates:
            destinations = [(float(c.donor.lat), float(c.donor.lng)) for c in matched_candidates]
            geo_results = geospatial_service.calculate_batch_distances_and_etas(origin, destinations)

        # 8. Deterministic Ranking:
        # 1. Estimated driving time (etaMinutes), ascending.
        # 2. Road distance (roadDistanceKm), ascending, when driving times are equal.
        # 3. Stable donor ID as deterministic tie-breaker.
        paired_candidates = list(zip(matched_candidates, geo_results))

        def ranking_key(item: Tuple[CandidateEvaluation, Dict[str, Any]]) -> Tuple[float, float, str]:
            cand, geo = item
            eta_val = geo.get("eta_minutes")
            sort_eta = float(eta_val) if eta_val is not None else float("inf")
            road_val = geo.get("road_distance_km")
            sort_road = (
                float(road_val)
                if road_val is not None
                else (cand.distance_km if cand.distance_km is not None else float("inf"))
            )
            donor_id = str(cand.donor.id)
            return (sort_eta, sort_road, donor_id)

        paired_candidates.sort(key=ranking_key)

        donor_responses: List[DonorResponse] = []
        for rank_idx, (cand, geo) in enumerate(paired_candidates, start=1):
            d = cand.donor
            coords = None
            if cand.has_valid_coordinates and d.lat is not None and d.lng is not None:
                if not mask_coords and d.location_consent_granted:
                    coords = Coordinates(lat=d.lat, lng=d.lng)

            road_km = geo.get("road_distance_km")
            haversine_km = cand.distance_km
            eta_mins = geo.get("eta_minutes")
            dist_source = geo.get("distance_source", "simulated_heuristic_fallback")
            eta_source = geo.get("eta_source", "simulated_heuristic_fallback")
            is_live = bool(geo.get("is_live_traffic") or geo.get("is_live_estimate", False))
            # Backward compatible distanceKm: road_km if available, otherwise straight-line haversine
            dist_km = road_km if road_km is not None else haversine_km

            hist_rate = int(round(cand.history_score)) if cand.has_observed_history else 0

            donor_responses.append(
                DonorResponse(
                    id=d.id,
                    bloodGroup=d.blood_group,
                    distanceKm=dist_km,
                    straightLineDistanceKm=haversine_km,
                    roadDistanceKm=road_km,
                    etaMinutes=eta_mins,
                    distanceSource=dist_source,
                    etaSource=eta_source,
                    isLiveEstimate=is_live,
                    eligibility=d.eligibility,
                    eligibilityReason=d.eligibility_reason,
                    responseProbability=cand.total_score,
                    reliabilityScore=int(round(cand.availability_score * 0.6 + cand.history_score * 0.4)),
                    reachabilityScore=int(round(cand.proximity_score)),
                    aiRank=rank_idx,
                    status=d.status,
                    locationConsentGranted=d.location_consent_granted,
                    lastDonationDays=d.last_donation_days,
                    historicalAcceptanceRate=hist_rate,
                    contactedAt=d.contacted_at,
                    respondedAt=d.responded_at,
                    coordinates=coords,
                )
            )

        # Unlocalized donors (missing coordinates) kept strictly separate from localized radius-bounded candidates
        unlocalized_responses: List[DonorResponse] = []
        for cand in unlocalized_candidates:
            d = cand.donor
            coords = None
            if cand.has_valid_coordinates and d.lat is not None and d.lng is not None:
                if not mask_coords and d.location_consent_granted:
                    coords = Coordinates(lat=d.lat, lng=d.lng)
            hist_rate = int(round(cand.history_score)) if cand.has_observed_history else 0
            unlocalized_responses.append(
                DonorResponse(
                    id=d.id,
                    bloodGroup=d.blood_group,
                    distanceKm=None,
                    straightLineDistanceKm=None,
                    roadDistanceKm=None,
                    etaMinutes=None,
                    distanceSource="unavailable_missing_coordinates",
                    etaSource="unavailable_missing_coordinates",
                    isLiveEstimate=False,
                    eligibility=d.eligibility,
                    eligibilityReason=d.eligibility_reason,
                    responseProbability=cand.total_score,
                    reliabilityScore=int(round(cand.availability_score * 0.6 + cand.history_score * 0.4)),
                    reachabilityScore=int(round(cand.proximity_score)),
                    aiRank=999,
                    status=d.status,
                    locationConsentGranted=d.location_consent_granted,
                    lastDonationDays=d.last_donation_days,
                    historicalAcceptanceRate=hist_rate,
                    contactedAt=d.contacted_at,
                    respondedAt=d.responded_at,
                    coordinates=coords,
                )
            )

        search_config = DonorSearchConfig(
            initialRadiusKm=initial_radius,
            currentRadiusKm=current_radius,
            maxRadiusKm=max_radius,
            expansionCount=expansion_count,
            expansionReason=expansion_reason,
        )

        if not matched_candidates:
            recommendation = (
                f"No eligible compatible donors found for recipient blood group {recipient_group} within {max_radius:.1f}km. "
                f"All {len(excluded_candidates)} evaluated donors were excluded due to compatibility mismatch, medical deferral, unavailability, or exceeding {max_radius:.1f}km."
            )
        else:
            top_resp = donor_responses[0]
            recommendation = (
                f"Progressive radius search reached {current_radius:.1f}km ({expansion_count} expansion(s)). "
                f"Candidate #{top_resp.id} ranked #1 with driving ETA {top_resp.etaMinutes} min ({top_resp.roadDistanceKm} km road distance). "
                f"Routing source: {top_resp.etaSource}."
            )

        if is_unknown_blood_group:
            recommendation = (
                "[EMERGENCY TRAUMA PROTOCOL: Recipient blood group unconfirmed in dispatch; emergency uncrossmatched "
                "universal O- matching applied pending formal pre-transfusion laboratory crossmatching.] " + recommendation
            )

        return RankedDonorsResponse(
            donors=donor_responses,
            searchConfig=search_config,
            aiRecommendation=recommendation,
            unlocalizedDonors=unlocalized_responses if unlocalized_responses else None,
        )

    @staticmethod
    def select_donors_for_emergency_contact(
        db: Session,
        emergency_id: str,
        max_donors: int = 3,
        current_user: Optional[UserProfileSchema] = None,
    ) -> List[Dict[str, Any]]:
        """
        Selects at most three distinct eligible donors for an emergency based on road ETA ranking.
        Maps selected donor slots to distinct test contacts only in mock/test mode.
        Does not overwrite donor records in the database, send real SMS/calls,
        or treat mock dispatches as donor acceptances.
        """
        bounded_max = min(max_donors, getattr(settings, "DONOR_SELECTION_MAX_CONTACTS", 3))
        ranked_res = DonorService.get_ranked_donors(db, emergency_id, current_user=current_user)
        selected_donors = ranked_res.donors[:bounded_max]

        test_pool = getattr(settings, "TEST_CONTACT_POOL", [
            "+919876543001",
            "+919876543002",
            "+919876543003",
            "+919876543004",
        ])

        results = []
        for idx, d in enumerate(selected_donors):
            test_number = test_pool[idx % len(test_pool)] if test_pool else None
            results.append({
                "slot": idx + 1,
                "donorId": d.id,
                "bloodGroup": d.bloodGroup,
                "etaMinutes": d.etaMinutes,
                "roadDistanceKm": d.roadDistanceKm,
                "straightLineDistanceKm": d.straightLineDistanceKm,
                "aiRank": d.aiRank,
                "testContactPhone": test_number if (settings.MOCK_NOTIFICATIONS_ONLY or settings.NOTIFICATION_PROVIDER == "mock") else None,
                "isTestContactMapped": bool(test_number and (settings.MOCK_NOTIFICATIONS_ONLY or settings.NOTIFICATION_PROVIDER == "mock")),
                "realDonorPhonePreserved": True,
            })
        return results

    @staticmethod
    def select_emergency_donor_batch(
        db: Session,
        emergency_id: str,
        batch_size: int = 5,
        exclude_previously_contacted: bool = True,
        current_user: Optional[UserProfileSchema] = None,
    ) -> Dict[str, Any]:
        """
        Selects up to batch_size (default 5) nearest eligible, compatible donors for an emergency.
        - Uses Haversine straight-line distance from patient emergency coordinates (no Google Maps road routes calculated here).
        - Google Maps road routes and ETA are calculated ONLY for donors who explicitly accept.
        - Prevents duplicate contacts for the same emergency by excluding previously contacted donors.
        - Progressively expands search radius across tiers [2.0, 5.0, 10.0, 20.0] if fewer than batch_size donors are available.
        - When at least 5 donors are available, selects 5. When fewer are available, selects all available in the reached tier.
        """
        emergency = db.query(Emergency).filter(Emergency.id == emergency_id).first()
        if not emergency:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Emergency '{emergency_id}' not found")
        if emergency.type != "blood":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Emergency '{emergency_id}' is not a blood emergency")

        raw_lat = getattr(emergency, "location_lat", None)
        raw_lng = getattr(emergency, "location_lng", None)
        if raw_lat is None or raw_lng is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Patient emergency coordinates are missing or invalid; cannot perform location-based proximity matching",
            )
        validate_coordinates(float(raw_lat), float(raw_lng))
        origin = (float(raw_lat), float(raw_lng))

        contacted_ids = set()
        if exclude_previously_contacted:
            contacted_rows = db.query(DonorEmergencyInteraction.donor_id).filter(
                DonorEmergencyInteraction.emergency_id == emergency_id
            ).all()
            contacted_ids = {row[0] for row in contacted_rows}

        recipient_group = emergency.blood_group.strip().upper() if emergency.blood_group else "O-"
        compatible_groups = get_compatible_donor_blood_groups(recipient_group)

        donors = db.query(Donor).all()
        eligible_candidates = []
        for d in donors:
            if d.id in contacted_ids:
                continue
            if (d.eligibility or "").lower() != "eligible":
                continue
            if d.status not in ["available", "eligible"]:
                continue
            if getattr(d, "is_synthetic", False):
                continue
            if compatible_groups is not None and d.blood_group:
                if d.blood_group.strip().upper() not in compatible_groups:
                    continue
            if d.lat is None or d.lng is None:
                continue
            try:
                validate_coordinates(float(d.lat), float(d.lng))
                dist_km = calculate_haversine_distance(origin, (float(d.lat), float(d.lng)))
                eligible_candidates.append({
                    "donor": d,
                    "distanceKm": round(dist_km, 2),
                })
            except Exception:
                continue

        eligible_candidates.sort(key=lambda x: (x["distanceKm"], str(x["donor"].id)))

        tiers = getattr(settings, "DONOR_SEARCH_EXPANSION_TIERS", [2.0, 5.0, 10.0, 20.0])
        tiers = sorted(list(set(tiers)))
        current_radius = tiers[0]
        expansion_count = 0
        selected_tier_candidates = []

        for tier_idx, radius in enumerate(tiers):
            candidates_in_tier = [c for c in eligible_candidates if c["distanceKm"] <= radius]
            current_radius = radius
            expansion_count = tier_idx
            if len(candidates_in_tier) >= batch_size or (candidates_in_tier and len(candidates_in_tier) == len(eligible_candidates)):
                selected_tier_candidates = candidates_in_tier
                break
        else:
            current_radius = tiers[-1]
            expansion_count = len(tiers) - 1
            selected_tier_candidates = [c for c in eligible_candidates if c["distanceKm"] <= current_radius]

        selected_batch = selected_tier_candidates[:batch_size]

        return {
            "emergencyId": emergency_id,
            "selectedCandidates": selected_batch,
            "currentRadiusKm": current_radius,
            "expansionCount": expansion_count,
            "totalEligibleInRadius": len(selected_tier_candidates),
            "totalUncontactedEligible": len(eligible_candidates),
        }

    @staticmethod
    def dispatch_emergency_donor_batch(
        db: Session,
        emergency_id: str,
        batch_size: int = 5,
        current_user: Optional[UserProfileSchema] = None,
    ) -> DonorBatchDispatchResponse:
        """
        Dispatches mock notifications to the next batch of up to 5 nearest eligible uncontacted donors.
        1. Checks current accepted donor count (aiming for 3 accepted donors).
        2. If 3 or more have already accepted, stops without dispatching unnecessary contacts.
        3. If fewer than 3 accepted, selects up to 5 nearest eligible uncontacted donors.
        4. Progressively expands search radius if fewer than 5 donors available in lower tiers.
        5. Sends mock notifications with carrier isolation, maps to test contact pool, records interactions.
        6. Strictly avoids duplicate contacts for the same emergency.
        7. Google Maps routes are calculated ONLY when donors explicitly accept.
        """
        emergency = db.query(Emergency).filter(Emergency.id == emergency_id).first()
        if not emergency:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Emergency '{emergency_id}' not found")
        if emergency.type != "blood":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Emergency '{emergency_id}' is not a blood emergency")

        target_accepted = getattr(settings, "DONOR_TARGET_ACCEPTED", 3)

        accepted_interactions = db.query(DonorEmergencyInteraction).filter(
            DonorEmergencyInteraction.emergency_id == emergency_id,
            DonorEmergencyInteraction.acceptance_status == "accepted",
        ).all()
        accepted_count = len(accepted_interactions)

        if accepted_count >= target_accepted:
            return DonorBatchDispatchResponse(
                emergencyId=emergency_id,
                batchNumber=0,
                donorsContactedCount=0,
                contactedDonors=[],
                currentRadiusKm=0.0,
                expansionCount=0,
                acceptedDonorsCount=accepted_count,
                targetAcceptedDonors=target_accepted,
                targetReached=True,
                message=f"Target threshold of {target_accepted} accepted donor(s) already reached ({accepted_count} accepted). No new dispatch batch required.",
            )

        existing_count = db.query(DonorEmergencyInteraction).filter(
            DonorEmergencyInteraction.emergency_id == emergency_id
        ).count()
        batch_num = (existing_count // batch_size) + 1

        selection_info = DonorService.select_emergency_donor_batch(
            db,
            emergency_id=emergency_id,
            batch_size=batch_size,
            exclude_previously_contacted=True,
            current_user=current_user,
        )

        selected = selection_info["selectedCandidates"]
        current_radius = selection_info["currentRadiusKm"]
        expansion_count = selection_info["expansionCount"]

        if not selected:
            return DonorBatchDispatchResponse(
                emergencyId=emergency_id,
                batchNumber=batch_num,
                donorsContactedCount=0,
                contactedDonors=[],
                currentRadiusKm=current_radius,
                expansionCount=expansion_count,
                acceptedDonorsCount=accepted_count,
                targetAcceptedDonors=target_accepted,
                targetReached=False,
                message="No additional uncontacted eligible donors available within maximum search radius.",
            )

        now_str = datetime.now(timezone.utc).isoformat()
        test_pool = getattr(settings, "TEST_CONTACT_POOL", [
            "+919876543001",
            "+919876543002",
            "+919876543003",
            "+919876543004",
            "+919876543005",
        ])
        actor_name = current_user.name if current_user else "LifeLink Dispatcher"
        actor_role = current_user.role if current_user else "hospital_staff"
        contacted_summaries: List[ContactedDonorSummary] = []
        contacted_recipients_in_batch = set()


        for idx, item in enumerate(selected):
            d = item["donor"]
            dist = item["distanceKm"]
            mapped_test = test_pool[idx % len(test_pool)] if test_pool else None
            recipient_target = mapped_test or (d.contact_number if d.contact_number else f"Donor #{d.id} ({d.blood_group})")

            # Notification deduplication guard: never alert the same phone number multiple times in a single batch
            if recipient_target in contacted_recipients_in_batch:
                continue
            contacted_recipients_in_batch.add(recipient_target)

            dispatch_success = True
            dispatch_error = None
            try:
                mock_notification_provider.dispatch(
                    recipient=recipient_target,
                    message=f"LifeLink Urgent Blood Emergency: Compatible donor needed for emergency {emergency_id}",
                    channel="sms",
                    metadata={
                        "emergency_id": emergency_id,
                        "donor_id": d.id,
                        "mapped_test_contact": mapped_test,
                        "batch_number": batch_num,
                        "real_donor_phone_preserved": True,
                    },
                )
            except Exception as exc:
                dispatch_success = False
                dispatch_error = str(exc)
                logger.error(f"Notification dispatch failed for donor {d.id}: {exc}")

            d.status = "contacted" if dispatch_success else d.status
            if dispatch_success:
                d.contacted_at = now_str

            now_dt = datetime.now(timezone.utc)
            inter = DonorEmergencyInteraction(
                id=f"dint-{uuid.uuid4().hex[:12]}",
                emergency_id=emergency_id,
                donor_id=d.id,
                selected_at=now_str,
                distance_km=dist,
                eta_minutes=None,
                time_of_day_hours=round(now_dt.hour + (now_dt.minute / 60.0), 2),
                day_of_week=now_dt.weekday(),
                emergency_priority=emergency.priority if emergency else "critical",
                compatibility_match_type="identical",
                donor_availability_at_selection="available",
                donor_total_previous_donations=0,
                donor_days_since_last_donation=d.last_donation_days,
                contact_status="attempted" if dispatch_success else "failed",
                contact_channel="sms",
                contact_attempted_at=now_str if dispatch_success else None,
                response_status="pending" if dispatch_success else "failed",
                acceptance_status="pending" if dispatch_success else "unreachable",
                completion_status="pending",
                outcome_source="dispatcher_portal",
                data_provenance=getattr(d, "data_provenance", "production"),
                is_synthetic=getattr(d, "is_synthetic", False),
                created_at=now_str,
                updated_at=now_str,
            )
            db.add(inter)

            evt = EmergencyEvent(
                id=f"evt-{uuid.uuid4().hex[:10]}",
                emergency_id=emergency_id,
                timestamp=now_str,
                actor=actor_name,
                action=(
                    f"Batch {batch_num}: Contacted Donor #{d.id} ({d.blood_group}) at {dist}km"
                    if dispatch_success
                    else f"Batch {batch_num}: Contact failed for Donor #{d.id} ({d.blood_group}): {dispatch_error}"
                ),
                resource=f"Donor #{d.id}",
                authorization=f"Role: {actor_role}",
                status="success" if dispatch_success else "failed",
            )
            db.add(evt)

            if dispatch_success:
                contacted_summaries.append(
                    ContactedDonorSummary(
                        donorId=d.id,
                        bloodGroup=d.blood_group,
                        distanceKm=dist,
                        contactedAt=now_str,
                        testContactPhone=mapped_test,
                    )
                )


        audit = AuditLog(
            id=f"audit-batch-{uuid.uuid4().hex[:10]}",
            timestamp=now_str,
            actor=actor_name,
            actor_type="user",
            action=f"Dispatched batch {batch_num} ({len(contacted_summaries)} donors) for emergency {emergency_id}",
            resource=f"Emergency #{emergency_id}",
            resource_id=emergency_id,
            authorization=f"Role: {actor_role}",
            status="success",
            module="blood",
        )
        db.add(audit)
        db.commit()

        return DonorBatchDispatchResponse(
            emergencyId=emergency_id,
            batchNumber=batch_num,
            donorsContactedCount=len(contacted_summaries),
            contactedDonors=contacted_summaries,
            currentRadiusKm=current_radius,
            expansionCount=expansion_count,
            acceptedDonorsCount=accepted_count,
            targetAcceptedDonors=target_accepted,
            targetReached=False,
            message=(
                f"Dispatched batch {batch_num} with {len(contacted_summaries)} donor(s) within {current_radius:.1f}km radius. "
                f"Current accepted donors: {accepted_count}/{target_accepted}."
            ),
        )

    @staticmethod
    def get_emergency_workflow_status(
        db: Session,
        emergency_id: str,
    ) -> DonorWorkflowStatusResponse:
        """
        Returns real-time status of donor outreach workflow for an emergency.
        """
        emergency = db.query(Emergency).filter(Emergency.id == emergency_id).first()
        if not emergency:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Emergency '{emergency_id}' not found")

        interactions = db.query(DonorEmergencyInteraction).filter(
            DonorEmergencyInteraction.emergency_id == emergency_id
        ).all()

        total_contacted = len(interactions)
        total_accepted = sum(1 for i in interactions if i.acceptance_status == "accepted" and not getattr(i, "is_synthetic", False))
        total_declined = sum(1 for i in interactions if i.acceptance_status in ["declined", "unreachable"] and not getattr(i, "is_synthetic", False))
        total_pending = sum(1 for i in interactions if i.acceptance_status == "pending" and not getattr(i, "is_synthetic", False))


        target_accepted = getattr(settings, "DONOR_TARGET_ACCEPTED", 3)
        target_reached = (total_accepted >= target_accepted)

        distances = [i.distance_km for i in interactions if i.distance_km is not None]
        current_radius = max(distances) if distances else getattr(settings, "DONOR_SEARCH_INITIAL_RADIUS_KM", 2.0)
        max_radius = getattr(settings, "DONOR_SEARCH_MAX_RADIUS_KM", 20.0)
        can_expand = (not target_reached and current_radius < max_radius)

        return DonorWorkflowStatusResponse(
            emergencyId=emergency_id,
            totalContacted=total_contacted,
            totalAccepted=total_accepted,
            totalDeclined=total_declined,
            totalPending=total_pending,
            targetAcceptedDonors=target_accepted,
            targetReached=target_reached,
            currentRadiusKm=current_radius,
            canExpandRadius=can_expand,
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
        test_pool = getattr(settings, "TEST_CONTACT_POOL", [])
        mapped_test_contact = None
        if (settings.MOCK_NOTIFICATIONS_ONLY or settings.NOTIFICATION_PROVIDER == "mock") and test_pool:
            # Map donor ID deterministically to one of the 4 test pool numbers
            mapped_test_contact = test_pool[abs(hash(donor.id)) % len(test_pool)]

        mock_recipient = mapped_test_contact if mapped_test_contact else f"Donor #{donor.id} ({donor.blood_group})"

        mock_notification_provider.dispatch(
            recipient=mock_recipient,
            message=f"LifeLink Urgent Blood Emergency: Compatible donor needed for emergency {emergency_id}",
            channel="sms",
            metadata={
                "emergency_id": emergency_id,
                "donor_id": donor_id,
                "actor": current_user.name,
                "mapped_test_contact": mapped_test_contact,
                "real_donor_phone_preserved": True,
            },
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

        VALID_RESPONSES = {"accepted", "declined", "en_route", "unavailable", "no_response"}
        if status_choice not in VALID_RESPONSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid response status '{status_choice}'. Must be one of: {', '.join(sorted(VALID_RESPONSES))}",
            )

        # Authorization: When caller is provided (REST endpoint), enforce role/identity validation
        if current_user:
            if current_user.role == "donor":
                if not donor.user_id or donor.user_id != current_user.id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Donors can only submit responses for their own profile",
                    )
            elif current_user.role not in ["doctor", "hospital_staff", "admin"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Unauthorized: Role '{current_user.role}' cannot record donor responses",
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
                    # Simulated acceptance separation:
                    # Simulated acceptances must never count as real production donor acceptances
                    if getattr(donor, "is_synthetic", False) or getattr(donor, "data_provenance", "production") != "production":
                        active_int.acceptance_status = "simulated_accepted"
                        active_int.is_synthetic = True
                        active_int.data_provenance = donor.data_provenance or "synthetic_demo"
                    else:
                        active_int.acceptance_status = "accepted"
                        active_int.is_synthetic = False
                        active_int.data_provenance = "production"

                    # Calculate Google Maps route only for donors who explicitly accept
                    if active_int.emergency_id and donor.lat is not None and donor.lng is not None:
                        emerg = db.query(Emergency).filter(Emergency.id == active_int.emergency_id).first()
                        if emerg and emerg.hospital_id:
                            hosp = db.query(Hospital).filter(Hospital.id == emerg.hospital_id).first()
                            if hosp and hosp.lat is not None and hosp.lng is not None:
                                try:
                                    geo = geospatial_service.calculate_distance_and_eta_sync(
                                        origin=(float(donor.lat), float(donor.lng)),
                                        destination=(float(hosp.lat), float(hosp.lng)),
                                    )
                                    if geo.get("road_distance_km") is not None:
                                        active_int.distance_km = geo.get("road_distance_km")
                                        donor.distance_km = geo.get("road_distance_km")
                                    if geo.get("eta_minutes") is not None:
                                        active_int.eta_minutes = geo.get("eta_minutes")
                                        donor.eta_minutes = geo.get("eta_minutes")
                                except Exception as err:
                                    logger.warning(f"Could not calculate road ETA for accepted donor {donor.id}: {err}")
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
        return DonorService._map_donor_to_response(donor, mask_coordinates=False, is_self=True)

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

    @staticmethod
    def set_donor_availability(
        db: Session,
        data: DonorAvailabilityRequest,
        current_user: UserProfileSchema,
    ) -> dict:
        allowed_statuses = {"available", "unavailable", "paused"}
        status_val = data.status.strip().lower()
        if status_val not in allowed_statuses:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid availability status '{data.status}'. Allowed values: {', '.join(sorted(allowed_statuses))}",
            )

        donor = db.query(Donor).filter((Donor.user_id == current_user.id) | (Donor.id == current_user.id)).first()
        if not donor:
            raise HTTPException(status_code=404, detail="Donor profile not found for current user")

        donor.status = status_val
        now_str = datetime.now(timezone.utc).isoformat()

        audit = AuditLog(
            id=f"audit-{int(datetime.now(timezone.utc).timestamp() * 1000) % 100000}",
            timestamp=now_str,
            actor=current_user.name,
            actor_type="donor",
            action=f"Updated availability status to {status_val}",
            resource="Donor Availability",
            resource_id=donor.id,
            authorization="Self-Managed Availability",
            status="success",
            module="donors",
        )
        db.add(audit)
        db.commit()
        db.refresh(donor)

        return {
            "status": donor.status,
            "message": f"Availability updated to {donor.status}",
            "donorId": donor.id,
        }

    @staticmethod
    async def get_accepted_donors_ranking(
        db: Session,
        emergency_id: str,
        current_user: UserProfileSchema,
    ) -> EmergencyAcceptedDonorsRankingResponse:
        """
        Ranks donors who have explicitly accepted a particular blood emergency by estimated arrival time.
        """
        # 1. Verify emergency exists
        emergency = db.query(Emergency).filter(Emergency.id == emergency_id).first()
        if not emergency:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Emergency '{emergency_id}' not found",
            )

        # 2. Confirm emergency is a blood request
        if emergency.type != "blood":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Emergency '{emergency_id}' is of type '{emergency.type}', not 'blood'. Accepted donor ranking is only supported for blood emergencies.",
            )

        # 3. Validate request status according to existing lifecycle
        if emergency.status in ["cancelled", "resolved"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot rank accepted donors for emergency '{emergency_id}' with inactive lifecycle status '{emergency.status}'",
            )

        # 4. Resolve destination hospital coordinates
        destination_hospital = None
        destination_coords: Optional[Tuple[float, float]] = None
        if emergency.hospital_id:
            destination_hospital = db.query(Hospital).filter(Hospital.id == emergency.hospital_id).first()
            if destination_hospital and destination_hospital.lat is not None and destination_hospital.lng is not None:
                try:
                    validate_coordinates(float(destination_hospital.lat), float(destination_hospital.lng))
                    destination_coords = (float(destination_hospital.lat), float(destination_hospital.lng))
                except Exception:
                    destination_coords = None

        # 5. Query interaction records explicitly marked as accepted for this emergency
        interactions = (
            db.query(DonorEmergencyInteraction)
            .filter(
                DonorEmergencyInteraction.emergency_id == emergency_id,
                DonorEmergencyInteraction.acceptance_status == "accepted",
            )
            .order_by(
                desc(DonorEmergencyInteraction.responded_at),
                desc(DonorEmergencyInteraction.selected_at),
            )
            .all()
        )

        # 6. Deduplicate, filter, and calculate arrival estimates
        seen_donors = set()
        accepted_entries: List[AcceptedDonorRankingEntry] = []

        compatible_groups = (
            get_compatible_donor_blood_groups(emergency.blood_group)
            if emergency.blood_group
            else None
        )

        for inter in interactions:
            donor_id = inter.donor_id
            if donor_id in seen_donors:
                continue
            seen_donors.add(donor_id)

            # Exclude interactions with terminal ineligible/cancelled completion status
            if inter.completion_status in ["canceled", "medically_deferred", "did_not_arrive"]:
                continue

            donor = db.query(Donor).filter(Donor.id == donor_id).first()
            if not donor:
                continue

            # Clinical eligibility check
            if donor.eligibility == "ineligible":
                continue

            # ABO/Rh compatibility safety preservation
            if compatible_groups is not None and donor.blood_group:
                if donor.blood_group.strip().upper() not in compatible_groups:
                    continue

            # Provenance: timestamp of acceptance
            acceptance_ts = inter.responded_at or donor.responded_at or inter.updated_at

            route_distance_km: Optional[float] = None
            estimated_duration_mins: Optional[int] = None
            eta_method: str = "unavailable_missing_coordinates"
            is_live: bool = False
            eta_available: bool = False

            if (
                destination_coords is not None
                and donor.lat is not None
                and donor.lng is not None
            ):
                try:
                    donor_coords = (float(donor.lat), float(donor.lng))
                    validate_coordinates(donor_coords[0], donor_coords[1])

                    geo_res = await geospatial_service.calculate_distance_and_eta(
                        origin=donor_coords,
                        destination=destination_coords,
                    )
                    route_distance_km = geo_res.get("road_distance_km")
                    estimated_duration_mins = geo_res.get("eta_minutes")
                    eta_method = geo_res.get("mode", "simulated_heuristic_fallback")
                    is_live = bool(geo_res.get("is_live_traffic", False))
                    eta_available = (estimated_duration_mins is not None)
                except Exception as ex:
                    logger.warning(
                        f"ETA calculation failed for accepted donor '{donor_id}' "
                        f"in emergency '{emergency_id}': {ex}"
                    )
                    route_distance_km = None
                    estimated_duration_mins = None
                    eta_method = "unavailable_routing_error"
                    is_live = False
                    eta_available = False
            else:
                eta_method = "unavailable_missing_coordinates"
                is_live = False
                eta_available = False

            entry = AcceptedDonorRankingEntry(
                donorId=donor.id,
                bloodGroup=donor.blood_group,
                acceptanceStatus="accepted",
                acceptedAt=acceptance_ts,
                routeDistanceKm=route_distance_km,
                estimatedTravelDurationMinutes=estimated_duration_mins,
                etaCalculationMethod=eta_method,
                isLiveEstimate=is_live,
                etaAvailable=eta_available,
                transitStatusNote="Donor has explicitly accepted emergency request; physical transit has not begun",
            )
            accepted_entries.append(entry)

        # 7. Rank accepted donors: shortest estimated travel duration first;
        #    donors with unavailable ETA sorted deterministically at the end
        def ranking_sort_key(item: AcceptedDonorRankingEntry):
            if item.etaAvailable and item.estimatedTravelDurationMinutes is not None:
                return (0, item.estimatedTravelDurationMinutes, item.routeDistanceKm or 0.0, item.donorId)
            else:
                return (1, 999999, 999999.0, item.donorId)

        accepted_entries.sort(key=ranking_sort_key)

        now_str = datetime.now(timezone.utc).isoformat()
        return EmergencyAcceptedDonorsRankingResponse(
            emergencyId=emergency.id,
            destinationHospitalId=emergency.hospital_id,
            destinationHospitalName=destination_hospital.name if destination_hospital else emergency.hospital_name,
            rankingGeneratedAt=now_str,
            totalAcceptedDonors=len(accepted_entries),
            rankedDonors=accepted_entries,
        )


donor_service = DonorService()
