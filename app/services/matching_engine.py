"""
LifeLink Clinical Baseline Donor Matching & Deterministic Ranking Engine.

Design Principles:
1. Strict Separation: Clinical eligibility and ABO/Rh compatibility rules are hard filters
   that MUST be passed before any operational ranking is computed.
2. Clinical Safety: Rule-based compatibility is verified against clinical transfusion standards
   (AABB / WHO Whole Blood & Packed Red Blood Cells protocol).
3. Transparent Operational Scoring: Scores are deterministic and rule-based heuristics.
   They are NEVER presented as machine learning predictions.
4. Explainability: Every candidate evaluation contains explicit reasons for inclusion,
   distance calculations, coordinate validity, and score contributions.
5. Missing Data Integrity: Missing coordinates or historical outcomes are explicitly reported
   and never masked with fabricated values.
"""

import math
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass
from app.ai.interfaces import DonorRankingServiceInterface
from app.models.donor import Donor


# Clinically approved ABO & RhD blood compatibility matrix for Red Blood Cells / Whole Blood transfusion.
# Reference: AABB Technical Manual (20th Edition), WHO Blood Cold Chain Guidelines.
# Scope: Cellular component / Whole Blood matching (Recipient Group -> Set of Compatible Donor Groups).
RBC_COMPATIBILITY_MAP: Dict[str, Set[str]] = {
    "O-": {"O-"},
    "O+": {"O-", "O+"},
    "A-": {"O-", "A-"},
    "A+": {"O-", "O+", "A-", "A+"},
    "B-": {"O-", "B-"},
    "B+": {"O-", "O+", "B-", "B+"},
    "AB-": {"O-", "A-", "B-", "AB-"},
    "AB+": {"O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"},  # Universal recipient for RBC
}

# Fresh Frozen Plasma (FFP) Compatibility Matrix.
# Note: Plasma transfusion compatibility follows an INVERTED pattern (AB is universal donor, O is universal recipient)
# because donor plasma antibodies must not bind recipient red blood cell antigens.
PLASMA_COMPATIBILITY_MAP: Dict[str, Set[str]] = {
    "O-": {"O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"},
    "O+": {"O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"},
    "A-": {"A-", "A+", "AB-", "AB+"},
    "A+": {"A-", "A+", "AB-", "AB+"},
    "B-": {"B-", "B+", "AB-", "AB+"},
    "B+": {"B-", "B+", "AB-", "AB+"},
    "AB-": {"AB-", "AB+"},
    "AB+": {"AB-", "AB+"},
}

# Platelet Compatibility Matrix:
# In clinical transfusion medicine (AABB Standards / BSH Guidelines):
# 1. ABO-identical platelets are the gold standard to ensure optimal post-transfusion increment.
# 2. In emergency inventory dispatch, platelets suspended in plasma compatible with recipient red cells
#    are acceptable (Group AB is universal plasma donor; Group A is acceptable emergency alternative).
# 3. For RhD-negative recipients, RhD-negative platelets are strongly indicated to prevent anti-D
#    alloimmunization caused by trace donor red blood cell stroma.
PLATELET_COMPATIBILITY_MAP: Dict[str, Set[str]] = {
    "O-": {"O-", "A-", "B-", "AB-"},                              # Rh- plasma-compatible
    "O+": {"O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"},      # Universal plasma recipient
    "A-": {"A-", "AB-"},                                          # Rh- plasma-compatible
    "A+": {"A-", "A+", "AB-", "AB+"},
    "B-": {"B-", "AB-"},                                          # Rh- plasma-compatible
    "B+": {"B-", "B+", "AB-", "AB+"},
    "AB-": {"AB-"},                                               # Rh- ABO-identical
    "AB+": {"AB-", "AB+"},
}

SUPPORTED_CELLULAR_COMPONENTS = {"red_blood_cells", "whole_blood", "prbc", "rbc"}
SUPPORTED_PLASMA_COMPONENTS = {"plasma", "fresh_frozen_plasma", "ffp"}
SUPPORTED_PLATELET_COMPONENTS = {"platelets", "platelet", "sdp", "rdp"}


def get_compatible_donor_blood_groups(
    recipient_blood_group: str,
    component: str = "red_blood_cells",
) -> Set[str]:
    """
    Returns the set of clinically compatible donor blood groups for a given recipient.
    Case-insensitive matching; strips extraneous whitespace.
    Supports component-specific protocols:
      - 'red_blood_cells' / 'whole_blood' / 'prbc' / 'rbc'
      - 'plasma' / 'fresh_frozen_plasma' / 'ffp'
      - 'platelets' / 'sdp' / 'rdp'
    CRITICAL SAFETY RULES:
    1. Returns an empty set for invalid or unrecognized blood group inputs.
    2. Returns an empty set for unsupported blood components (never silently falls back to an unrelated map).
    """
    normalized_group = recipient_blood_group.strip().upper() if recipient_blood_group else ""
    if not normalized_group:
        return set()

    normalized_comp = (component or "red_blood_cells").strip().lower().replace(" ", "_")

    if normalized_comp in SUPPORTED_PLASMA_COMPONENTS:
        return PLASMA_COMPATIBILITY_MAP.get(normalized_group, set())
    elif normalized_comp in SUPPORTED_PLATELET_COMPONENTS:
        return PLATELET_COMPATIBILITY_MAP.get(normalized_group, set())
    elif normalized_comp in SUPPORTED_CELLULAR_COMPONENTS:
        return RBC_COMPATIBILITY_MAP.get(normalized_group, set())
    else:
        # SAFETY FAIL-CLOSED: Unsupported components must NEVER silently default to RBC
        return set()



def haversine_distance_km(
    lat1: Optional[float], lng1: Optional[float],
    lat2: Optional[float], lng2: Optional[float]
) -> Optional[float]:
    """
    Computes great-circle distance between two geographic coordinates using the Haversine formula.
    Returns None if any coordinate is None or outside valid geographic ranges (-90..90, -180..180).
    Also returns None if coordinates represent Null Island (0.0, 0.0), indicating uninitialized GPS.
    """
    if lat1 is None or lng1 is None or lat2 is None or lng2 is None:
        return None

    try:
        lat1_f = float(lat1)
        lng1_f = float(lng1)
        lat2_f = float(lat2)
        lng2_f = float(lng2)
    except (TypeError, ValueError):
        return None

    # Null Island check: (0.0, 0.0) represents uninitialized GPS in clinical records
    if (lat1_f == 0.0 and lng1_f == 0.0) or (lat2_f == 0.0 and lng2_f == 0.0):
        return None

    if not (-90.0 <= lat1_f <= 90.0 and -90.0 <= lat2_f <= 90.0):
        return None
    if not (-180.0 <= lng1_f <= 180.0 and -180.0 <= lng2_f <= 180.0):
        return None

    # Earth radius in kilometers (WGS 84 mean radius)
    r = 6371.0088

    phi1 = math.radians(lat1_f)
    phi2 = math.radians(lat2_f)
    delta_phi = math.radians(lat2_f - lat1_f)
    delta_lambda = math.radians(lng2_f - lng1_f)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))

    return round(r * c, 2)


def estimate_urban_transit_eta(distance_km: Optional[float]) -> Optional[int]:
    """
    Computes a heuristic travel time estimate in minutes based on nominal urban transit speed
    (30 km/h) plus a fixed 3-minute mobilization buffer.
    IMPORTANT: This is a static heuristic calculation and MUST NOT be presented as live traffic telemetry.
    """
    if distance_km is None or distance_km < 0:
        return None
    # 30 km/h = 0.5 km/min -> transit_mins = distance * 2 + 3
    transit_mins = math.ceil((distance_km / 30.0) * 60.0 + 3.0)
    return int(max(3, transit_mins))


@dataclass
class CandidateEvaluation:
    donor: Donor
    is_compatible: bool
    is_eligible: bool
    is_available: bool
    distance_km: Optional[float]
    eta_minutes: Optional[int]
    has_valid_coordinates: bool
    has_observed_history: bool
    proximity_score: float
    availability_score: float
    history_score: float
    total_score: int
    rank: int
    exclusion_reason: Optional[str]
    explanation: str


class BaselineDonorMatchingEngine(DonorRankingServiceInterface):
    """
    Deterministic LifeLink Baseline Matching Engine.
    Implements rule-based clinical filtering followed by multi-attribute operational ranking.
    """

    # Scoring weights (must sum to 1.0)
    WEIGHT_PROXIMITY = 0.45
    WEIGHT_AVAILABILITY = 0.35
    WEIGHT_HISTORY = 0.20

    def evaluate_candidates(
        self,
        donors: List[Donor],
        recipient_blood_group: str,
        hospital_lat: Optional[float] = None,
        hospital_lng: Optional[float] = None,
        component: str = "red_blood_cells",
    ) -> Tuple[List[CandidateEvaluation], List[CandidateEvaluation]]:
        """
        Filters and ranks candidate donors.
        Returns:
            (ranked_eligible_candidates, excluded_candidates)
        """
        compatible_groups = get_compatible_donor_blood_groups(recipient_blood_group, component=component)
        eligible_candidates: List[CandidateEvaluation] = []
        excluded_candidates: List[CandidateEvaluation] = []

        for donor in donors:
            donor_group = donor.blood_group.strip().upper() if donor.blood_group else ""
            
            # 1. Compatibility Check
            is_compatible = donor_group in compatible_groups
            if not is_compatible:
                excluded_candidates.append(CandidateEvaluation(
                    donor=donor,
                    is_compatible=False,
                    is_eligible=False,
                    is_available=False,
                    distance_km=None,
                    eta_minutes=None,
                    has_valid_coordinates=False,
                    has_observed_history=False,
                    proximity_score=0.0,
                    availability_score=0.0,
                    history_score=0.0,
                    total_score=0,
                    rank=999,
                    exclusion_reason=f"Blood group {donor.blood_group} is incompatible with recipient group {recipient_blood_group} for {component}",
                    explanation=f"Incompatible blood group according to {component} compatibility protocol.",
                ))
                continue

            # 2. Clinical Eligibility Filter (Zero Override Tolerance)
            is_eligible = (donor.eligibility or "").lower() == "eligible"
            if not is_eligible:
                reason = donor.eligibility_reason or "Medical deferral / screening failure"
                excluded_candidates.append(CandidateEvaluation(
                    donor=donor,
                    is_compatible=True,
                    is_eligible=False,
                    is_available=False,
                    distance_km=None,
                    eta_minutes=None,
                    has_valid_coordinates=False,
                    has_observed_history=False,
                    proximity_score=0.0,
                    availability_score=0.0,
                    history_score=0.0,
                    total_score=0,
                    rank=999,
                    exclusion_reason=f"Clinically deferred: {reason}",
                    explanation=f"Excluded from dispatch due to medical eligibility status: {donor.eligibility} ({reason})",
                ))
                continue

            # 3. Operational Availability Filter
            status_clean = (donor.status or "").lower()
            is_available = status_clean in ("available", "on-call", "on_call", "contacted")
            if not is_available:
                excluded_candidates.append(CandidateEvaluation(
                    donor=donor,
                    is_compatible=True,
                    is_eligible=True,
                    is_available=False,
                    distance_km=None,
                    eta_minutes=None,
                    has_valid_coordinates=False,
                    has_observed_history=False,
                    proximity_score=0.0,
                    availability_score=0.0,
                    history_score=0.0,
                    total_score=0,
                    rank=999,
                    exclusion_reason=f"Operational status unavailable: {donor.status}",
                    explanation=f"Excluded because donor is currently marked as {donor.status}.",
                ))
                continue

            # 4. Geodesic Distance Calculation
            dist_km = haversine_distance_km(hospital_lat, hospital_lng, donor.lat, donor.lng)
            has_valid_coords = dist_km is not None
            if dist_km is not None:
                calc_dist = dist_km
                calc_eta = estimate_urban_transit_eta(dist_km)
                # Proximity score degrades smoothly by 4 points per km; minimum 0
                prox_score = max(0.0, min(100.0, 100.0 - (calc_dist * 4.0)))
                coord_detail = f"Geodesic distance: {calc_dist:.1f} km (heuristic transit ETA: ~{calc_eta} min; not live traffic telemetry)."
            else:
                calc_dist = None
                calc_eta = None
                prox_score = 50.0
                if donor.lat is None or donor.lng is None:
                    coord_detail = "Donor location coordinates missing; distance cannot be calculated, neutral distance baseline applied."
                elif hospital_lat is None or hospital_lng is None:
                    coord_detail = "Hospital location coordinates missing; distance cannot be calculated, neutral distance baseline applied."
                else:
                    coord_detail = "Coordinates invalid; neutral distance baseline applied."

            # 5. Availability Score Contribution
            if status_clean == "available":
                avail_score = 100.0
            elif status_clean in ("on-call", "on_call"):
                avail_score = 65.0
            else:
                avail_score = 75.0

            # 6. Historical Acceptance / Response Reliability
            # Explicitly do NOT fabricate a historical acceptance rate if unobserved!
            if donor.historical_acceptance_rate is not None and donor.historical_acceptance_rate > 0:
                has_history = True
                hist_score = float(min(100, max(0, donor.historical_acceptance_rate)))
                hist_detail = f"Observed historical acceptance: {int(hist_score)}%."
            else:
                has_history = False
                # Neutral baseline contribution for donors without recorded dispatch history
                hist_score = 50.0
                hist_detail = "No prior interaction history recorded; neutral historical baseline applied."

            # 7. Total Deterministic Score Computation
            raw_score = (
                (self.WEIGHT_PROXIMITY * prox_score)
                + (self.WEIGHT_AVAILABILITY * avail_score)
                + (self.WEIGHT_HISTORY * hist_score)
            )
            total_score = int(round(raw_score))

            # 8. Transparent Explanation String
            explanation_parts = [
                f"Rule-based operational score: {total_score}/100 (deterministic heuristic baseline; not an ML prediction).",
                f"Compatibility: {donor_group} -> {recipient_blood_group} ({component} matched).",
                coord_detail,
                f"Status: {donor.status} ({int(avail_score)}%).",
                hist_detail,
            ]
            explanation = " ".join(explanation_parts)

            eligible_candidates.append(CandidateEvaluation(
                donor=donor,
                is_compatible=True,
                is_eligible=True,
                is_available=True,
                distance_km=calc_dist,
                eta_minutes=calc_eta,
                has_valid_coordinates=has_valid_coords,
                has_observed_history=has_history,
                proximity_score=prox_score,
                availability_score=avail_score,
                history_score=hist_score,
                total_score=total_score,
                rank=0,  # Will be assigned upon sorting
                exclusion_reason=None,
                explanation=explanation,
            ))

        # Sort eligible candidates: highest score first; tiebreak by distance ascending; secondary tiebreak by donor ID
        eligible_candidates.sort(
            key=lambda c: (-c.total_score, c.distance_km if c.distance_km is not None else 999.0, c.donor.id)
        )

        # Assign ordinal ranks (1-indexed)
        for idx, candidate in enumerate(eligible_candidates, start=1):
            candidate.rank = idx

        return eligible_candidates, excluded_candidates

    async def rank_donors(
        self, emergency_id: str, candidate_donor_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Implementation of the DonorRankingServiceInterface abstract method.
        Returns serialized ranking dictionaries.
        """
        # Designed for asynchronous AI interface compatibility
        return [
            {
                "donorId": d_id,
                "aiRank": idx + 1,
                "scoreType": "deterministic_baseline_heuristic",
            }
            for idx, d_id in enumerate(candidate_donor_ids)
        ]


baseline_matching_engine = BaselineDonorMatchingEngine()
