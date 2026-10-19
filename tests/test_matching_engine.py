"""
Unit and Integration Tests for LifeLink Baseline Matching Engine
File: backend/tests/test_matching_engine.py

Validates:
1. Complete ABO/Rh blood group compatibility coverage (all 8 groups).
2. Strict separation of clinical eligibility and availability filtering from ranking.
3. Prioritization of available donors over on-call donors.
4. Haversine distance computation, invalid coordinate guards, and transit ETA estimation.
5. Explicit missing-coordinate handling (no silent distance fabrication).
6. Missing historical information handling (no fabricated 75% rate).
7. Empty candidate pool handling.
8. Deterministic scoring formula verification.
9. DonorRankingServiceInterface interface conformance.
"""

import pytest
from app.models.donor import Donor
from app.services.matching_engine import (
    baseline_matching_engine,
    haversine_distance_km,
    estimate_urban_transit_eta,
    get_compatible_donor_blood_groups,
    RBC_COMPATIBILITY_MAP,
    CandidateEvaluation,
)
from app.ai.interfaces import DonorRankingServiceInterface


# ---------------------------------------------------------------------------
# 1. ABO / Rh Blood Group Compatibility Matrix Tests (All 8 Groups)
# ---------------------------------------------------------------------------

def test_rbc_compatibility_matrix_all_eight_groups():
    """
    Clinically verifies all 8 ABO/Rh blood groups against the documented
    cellular component / Packed Red Blood Cell transfusion guidelines.
    """
    # 1. O- can only receive O- (Universal donor, restrictive recipient)
    assert get_compatible_donor_blood_groups("O-") == {"O-"}

    # 2. O+ can receive O- and O+
    assert get_compatible_donor_blood_groups("O+") == {"O-", "O+"}

    # 3. A- can receive O- and A-
    assert get_compatible_donor_blood_groups("A-") == {"O-", "A-"}

    # 4. A+ can receive O-, O+, A-, A+
    assert get_compatible_donor_blood_groups("A+") == {"O-", "O+", "A-", "A+"}

    # 5. B- can receive O- and B-
    assert get_compatible_donor_blood_groups("B-") == {"O-", "B-"}

    # 6. B+ can receive O-, O+, B-, B+
    assert get_compatible_donor_blood_groups("B+") == {"O-", "O+", "B-", "B+"}

    # 7. AB- can receive O-, A-, B-, AB-
    assert get_compatible_donor_blood_groups("AB-") == {"O-", "A-", "B-", "AB-"}

    # 8. AB+ is universal RBC recipient (all 8 blood groups)
    assert get_compatible_donor_blood_groups("AB+") == {
        "O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"
    }


def test_compatibility_case_and_whitespace_insensitivity():
    """Ensures input normalization handles lowercase, whitespace, and padding."""
    assert get_compatible_donor_blood_groups("  o-  ") == {"O-"}
    assert get_compatible_donor_blood_groups("ab+") == {
        "O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"
    }
    assert get_compatible_donor_blood_groups("a-") == {"O-", "A-"}


# ---------------------------------------------------------------------------
# 2. Hard Clinical Eligibility & Operational Availability Filtering
# ---------------------------------------------------------------------------

def test_clinical_eligibility_filtering():
    """Ineligible and pending_review donors must be excluded before ranking."""
    donors = [
        Donor(id="D-ELIG", blood_group="O-", eligibility="eligible", status="available", lat=12.97, lng=77.59),
        Donor(id="D-INELIG", blood_group="O-", eligibility="ineligible", eligibility_reason="Recent fever", status="available", lat=12.97, lng=77.59),
        Donor(id="D-REVIEW", blood_group="O-", eligibility="pending_review", eligibility_reason="Medication check", status="available", lat=12.97, lng=77.59),
    ]

    eligible, excluded = baseline_matching_engine.evaluate_candidates(donors, recipient_blood_group="O-")

    assert len(eligible) == 1
    assert eligible[0].donor.id == "D-ELIG"

    excluded_ids = {c.donor.id for c in excluded}
    assert "D-INELIG" in excluded_ids
    assert "D-REVIEW" in excluded_ids

    # Check reason captured
    inelig_cand = next(c for c in excluded if c.donor.id == "D-INELIG")
    assert "Recent fever" in inelig_cand.exclusion_reason


def test_operational_availability_filtering_and_prioritization():
    """
    Unavailable and declined donors must be excluded.
    Available donors must be prioritized above on-call donors when other attributes are equal.
    """
    hospital_lat, hospital_lng = 12.9716, 77.5946

    donor_avail = Donor(
        id="D-AVAIL", blood_group="O-", eligibility="eligible", status="available",
        lat=12.9716, lng=77.5946, historical_acceptance_rate=80
    )
    donor_oncall = Donor(
        id="D-ONCALL", blood_group="O-", eligibility="eligible", status="on-call",
        lat=12.9716, lng=77.5946, historical_acceptance_rate=80
    )
    donor_unavail = Donor(
        id="D-UNAVAIL", blood_group="O-", eligibility="eligible", status="unavailable",
        lat=12.9716, lng=77.5946
    )
    donor_declined = Donor(
        id="D-DECLINED", blood_group="O-", eligibility="eligible", status="declined",
        lat=12.9716, lng=77.5946
    )

    donors = [donor_oncall, donor_avail, donor_unavail, donor_declined]
    eligible, excluded = baseline_matching_engine.evaluate_candidates(
        donors, recipient_blood_group="O-", hospital_lat=hospital_lat, hospital_lng=hospital_lng
    )

    # 1. Unavailable and declined must be excluded
    assert len(eligible) == 2
    assert len(excluded) == 2
    excluded_ids = {c.donor.id for c in excluded}
    assert "D-UNAVAIL" in excluded_ids
    assert "D-DECLINED" in excluded_ids

    # 2. Available must be ranked higher than on-call (rank 1 vs rank 2)
    assert eligible[0].donor.id == "D-AVAIL"
    assert eligible[0].rank == 1
    assert eligible[0].availability_score == 100.0

    assert eligible[1].donor.id == "D-ONCALL"
    assert eligible[1].rank == 2
    assert eligible[1].availability_score == 65.0
    assert eligible[0].total_score > eligible[1].total_score


# ---------------------------------------------------------------------------
# 3. Distance Calculation & Missing Coordinate Handling
# ---------------------------------------------------------------------------

def test_haversine_formula_accuracy():
    """Verifies great-circle geodesic calculation with known coordinate pairs."""
    # Bengaluru City Center to Apollo Jayanagar (~4.7 km)
    dist = haversine_distance_km(12.9716, 77.5946, 12.9352, 77.6245)
    assert dist is not None
    assert 4.5 <= dist <= 5.2

    # Same location must yield 0.0 km
    assert haversine_distance_km(12.9716, 77.5946, 12.9716, 77.5946) == 0.0

    # Invalid latitude/longitude bounds must return None
    assert haversine_distance_km(95.0, 77.0, 12.0, 77.0) is None
    assert haversine_distance_km(12.0, -190.0, 12.0, 77.0) is None


def test_transit_eta_heuristic_labeling():
    """Ensures urban transit ETA calculation is documented as heuristic transit speed."""
    assert estimate_urban_transit_eta(0.0) == 3   # 3-minute mobilization buffer
    assert estimate_urban_transit_eta(5.0) == 13  # (5/30)*60 + 3 = 13 minutes
    assert estimate_urban_transit_eta(15.0) == 33 # (15/30)*60 + 3 = 33 minutes
    assert estimate_urban_transit_eta(None) is None


def test_missing_coordinates_handled_explicitly_without_fabrication():
    """
    Missing coordinates must NOT silently fabricate arbitrary distances.
    Must set distance_km=None, has_valid_coordinates=False, and note unobserved coords.
    """
    hospital_lat, hospital_lng = 12.9716, 77.5946

    donor_with_coords = Donor(
        id="D-COORDS", blood_group="O-", eligibility="eligible", status="available",
        lat=12.9600, lng=77.6000
    )
    donor_missing_coords = Donor(
        id="D-NOCOORDS", blood_group="O-", eligibility="eligible", status="available",
        lat=None, lng=None
    )

    donors = [donor_with_coords, donor_missing_coords]
    eligible, _ = baseline_matching_engine.evaluate_candidates(
        donors, recipient_blood_group="O-", hospital_lat=hospital_lat, hospital_lng=hospital_lng
    )

    cand_coords = next(c for c in eligible if c.donor.id == "D-COORDS")
    assert cand_coords.has_valid_coordinates is True
    assert cand_coords.distance_km is not None
    assert "Geodesic distance" in cand_coords.explanation

    cand_no_coords = next(c for c in eligible if c.donor.id == "D-NOCOORDS")
    assert cand_no_coords.has_valid_coordinates is False
    assert cand_no_coords.distance_km is None
    assert cand_no_coords.eta_minutes is None
    assert "coordinates missing" in cand_no_coords.explanation.lower()
    assert cand_no_coords.proximity_score == 50.0  # Neutral baseline


def test_missing_hospital_coordinates():
    """If requesting hospital coordinates are unobserved, distance is marked unobserved."""
    donor = Donor(
        id="D-1", blood_group="O-", eligibility="eligible", status="available",
        lat=12.97, lng=77.59
    )
    eligible, _ = baseline_matching_engine.evaluate_candidates(
        [donor], recipient_blood_group="O-", hospital_lat=None, hospital_lng=None
    )
    assert len(eligible) == 1
    assert eligible[0].distance_km is None
    assert eligible[0].has_valid_coordinates is False
    assert "hospital location coordinates missing" in eligible[0].explanation.lower()


# ---------------------------------------------------------------------------
# 4. Historical Information & Anti-Fabrication Safeguards
# ---------------------------------------------------------------------------

def test_missing_historical_acceptance_rate_is_explicit():
    """
    Ensures the system NEVER assigns an arbitrary 75% rate to unobserved donors.
    Missing history must be marked has_observed_history=False with neutral baseline 50.
    """
    donor_unobserved = Donor(
        id="D-NEW", blood_group="O-", eligibility="eligible", status="available",
        lat=12.97, lng=77.59, historical_acceptance_rate=0
    )
    donor_observed = Donor(
        id="D-EXPERIENCED", blood_group="O-", eligibility="eligible", status="available",
        lat=12.97, lng=77.59, historical_acceptance_rate=92
    )

    eligible, _ = baseline_matching_engine.evaluate_candidates(
        [donor_unobserved, donor_observed], recipient_blood_group="O-",
        hospital_lat=12.97, hospital_lng=77.59
    )

    c_unobserved = next(c for c in eligible if c.donor.id == "D-NEW")
    assert c_unobserved.has_observed_history is False
    assert c_unobserved.history_score == 50.0
    assert "no prior interaction history recorded" in c_unobserved.explanation.lower()
    # Explicit anti-fabrication check: must NOT be 75%
    assert c_unobserved.history_score != 75.0

    c_observed = next(c for c in eligible if c.donor.id == "D-EXPERIENCED")
    assert c_observed.has_observed_history is True
    assert c_observed.history_score == 92.0
    assert "Observed historical acceptance: 92%" in c_observed.explanation


# ---------------------------------------------------------------------------
# 5. Deterministic Scoring Formula & Weight Contribution
# ---------------------------------------------------------------------------

def test_deterministic_scoring_formula_weights():
    """
    Verifies that the total score exactly follows:
    Total = round(0.45 * Proximity + 0.35 * Availability + 0.20 * History)
    """
    donor = Donor(
        id="D-SCORE", blood_group="O-", eligibility="eligible", status="available",
        lat=12.9716, lng=77.5946, historical_acceptance_rate=100
    )
    # Distance = 0 km -> proximity_score = 100.0
    # Status = available -> availability_score = 100.0
    # History = 100 -> history_score = 100.0
    # Expected total = 100
    eligible, _ = baseline_matching_engine.evaluate_candidates(
        [donor], recipient_blood_group="O-",
        hospital_lat=12.9716, hospital_lng=77.5946
    )
    assert len(eligible) == 1
    assert eligible[0].proximity_score == 100.0
    assert eligible[0].availability_score == 100.0
    assert eligible[0].history_score == 100.0
    assert eligible[0].total_score == 100

    # Explanation must state heuristic rule-based baseline and not ML prediction
    assert "not an ml prediction" in eligible[0].explanation.lower()


# ---------------------------------------------------------------------------
# 6. Edge Cases: Empty Candidates & Blood Incompatibility
# ---------------------------------------------------------------------------

def test_empty_candidate_pool():
    """Empty candidate pool returns empty lists without exception."""
    eligible, excluded = baseline_matching_engine.evaluate_candidates([], recipient_blood_group="A+")
    assert eligible == []
    assert excluded == []


def test_all_candidates_incompatible():
    """If no candidates match recipient, eligible is empty and all are in excluded."""
    # Recipient O- cannot receive A+, B+, or AB+
    donors = [
        Donor(id="D-A", blood_group="A+", eligibility="eligible", status="available"),
        Donor(id="D-B", blood_group="B+", eligibility="eligible", status="available"),
        Donor(id="D-AB", blood_group="AB+", eligibility="eligible", status="available"),
    ]
    eligible, excluded = baseline_matching_engine.evaluate_candidates(donors, recipient_blood_group="O-")
    assert len(eligible) == 0
    assert len(excluded) == 3
    for exc in excluded:
        assert exc.is_compatible is False
        assert "incompatible" in exc.exclusion_reason.lower()


# ---------------------------------------------------------------------------
# 7. Conformance with AI Ranking Interface
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_matching_engine_interface_conformance():
    """Verifies abstract interface conformance for asynchronous integration."""
    assert isinstance(baseline_matching_engine, DonorRankingServiceInterface)
    rankings = await baseline_matching_engine.rank_donors("BL-102", ["D-101", "D-104"])
    assert len(rankings) == 2
    assert rankings[0]["donorId"] == "D-101"
    assert rankings[0]["aiRank"] == 1
    assert rankings[0]["scoreType"] == "deterministic_baseline_heuristic"


# ---------------------------------------------------------------------------
# 8. Clinical Safety Guards: Unrecognized Blood Groups & Deterministic Tiebreak
# ---------------------------------------------------------------------------

def test_unrecognized_blood_group_safe_rejection():
    """
    Verifies that unknown or invalid blood groups return an empty compatible set.
    Prevents corrupt or unrecognized strings from matching candidates.
    """
    assert get_compatible_donor_blood_groups("XYZ") == set()
    assert get_compatible_donor_blood_groups("") == set()
    assert get_compatible_donor_blood_groups("INVALID_TYPE") == set()

    donors = [
        Donor(id="D-O1", blood_group="O-", eligibility="eligible", status="available"),
        Donor(id="D-O2", blood_group="XYZ", eligibility="eligible", status="available"),
    ]
    eligible, excluded = baseline_matching_engine.evaluate_candidates(donors, recipient_blood_group="XYZ")
    # Both must be excluded because XYZ is an invalid clinical blood group
    assert len(eligible) == 0
    assert len(excluded) == 2


def test_deterministic_donor_id_tie_breaking():
    """
    When scores and distances are identical, ordering must be strictly deterministic
    based on donor.id.
    """
    donor_b = Donor(
        id="D-200", blood_group="O-", eligibility="eligible", status="available",
        lat=12.9716, lng=77.5946, historical_acceptance_rate=80
    )
    donor_a = Donor(
        id="D-100", blood_group="O-", eligibility="eligible", status="available",
        lat=12.9716, lng=77.5946, historical_acceptance_rate=80
    )
    donor_c = Donor(
        id="D-300", blood_group="O-", eligibility="eligible", status="available",
        lat=12.9716, lng=77.5946, historical_acceptance_rate=80
    )

    # Pass in unsorted order [D-300, D-200, D-100]
    eligible, _ = baseline_matching_engine.evaluate_candidates(
        [donor_c, donor_b, donor_a], recipient_blood_group="O-",
        hospital_lat=12.9716, hospital_lng=77.5946
    )

    assert len(eligible) == 3
    # Scores and distances are identical, so secondary tie-break by ID yields D-100, D-200, D-300
    assert [c.donor.id for c in eligible] == ["D-100", "D-200", "D-300"]
    assert [c.rank for c in eligible] == [1, 2, 3]
