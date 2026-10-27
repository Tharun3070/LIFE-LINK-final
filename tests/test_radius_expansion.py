"""
LifeLink Progressive Blood Donor Radius Expansion Test Suite.
File: tests/test_radius_expansion.py

Validates:
1. Suitable donors found within initial 2 km radius: no expansion (currentRadiusKm=2.0, expansionCount=0).
2. Insufficient candidates within 2 km: progressive expansion to 5 km (currentRadiusKm=5.0, expansionCount=1).
3. Expansion to 10 km when 2 km and 5 km tiers yield fewer than target candidate count.
4. Expansion to 20 km maximum when necessary (e.g., Coimbatore-Sulur corridor distance ~13 km).
5. Zero suitable donors anywhere within 20 km returns clear empty list with 20.0 km metadata.
6. Incompatible blood groups never qualify during any expansion tier.
7. Ineligible or unavailable donors never qualify during any expansion tier.
8. Donors located strictly outside the final reached radius are excluded.
9. No duplicate donors appear in the returned candidate list across expansion stages.
10. Missing and invalid coordinates do not fabricate distances (reported as unlocalized).
11. Search metadata accurately reports initial radius, current radius, max radius, expansion count, and reason.
12. Existing endpoint response compatibility on GET /api/v1/blood/donors/ranked.
13. Custom target candidate threshold (min_candidates) via query parameter.
"""

from datetime import datetime, timezone
import pytest
from app.models.donor import Donor
from app.models.emergency import Emergency
from app.models.hospital import Hospital


@pytest.fixture
def coimbatore_setup(db):
    """
    Sets up a realistic Coimbatore emergency scenario:
    Hospital: Kovai Medical Center and Hospital (KMCH) on Avinashi Road (11.0558, 77.0345).
    Emergency: O- critical trauma transfusion.
    """
    hospital = Hospital(
        id="hosp-kmch-cbe",
        name="Kovai Medical Center and Hospital (KMCH)",
        address="Avinashi Road, Civil Aerodrome Post",
        city="Coimbatore",
        lat=11.0558,
        lng=77.0345,
        type="Tertiary Trauma Care",
        blood_bank_available=True,
    )
    db.add(hospital)

    now_str = datetime.now(timezone.utc).isoformat()
    emergency = Emergency(
        id="BL-CBE-TRAUMA",
        type="blood",
        priority="critical",
        status="active",
        hospital_id="hosp-kmch-cbe",
        hospital_name="Kovai Medical Center and Hospital (KMCH)",
        created_at=now_str,
        updated_at=now_str,
        description="Coimbatore trauma center: Acute blood request O-",
        blood_group="O-",
        units_required=2,
        location_lat=11.0558,
        location_lng=77.0345,
    )
    db.add(emergency)
    db.commit()
    return hospital, emergency


def test_radius_no_expansion_when_initial_tier_satisfied(client, coimbatore_setup, db):
    """
    KMCH is at (11.0558, 77.0345).
    When 3 compatible, eligible donors are within 2.0 km (Peelamedu cluster),
    the search must stop at 2.0 km with expansionCount=0.
    """
    # 3 donors within ~1.2 km of KMCH
    d1 = Donor(id="D-CBE-01", blood_group="O-", eligibility="eligible", status="available", lat=11.0520, lng=77.0310) # ~0.57 km
    d2 = Donor(id="D-CBE-02", blood_group="O-", eligibility="eligible", status="available", lat=11.0580, lng=77.0380) # ~0.46 km
    d3 = Donor(id="D-CBE-03", blood_group="O-", eligibility="eligible", status="available", lat=11.0480, lng=77.0290) # ~1.05 km
    # 1 donor far away (at 8 km)
    d4 = Donor(id="D-CBE-FAR", blood_group="O-", eligibility="eligible", status="available", lat=11.0180, lng=76.9680) # ~8.3 km
    db.add_all([d1, d2, d3, d4])
    db.commit()

    resp = client.get("/api/v1/blood/donors/ranked?emergencyId=BL-CBE-TRAUMA&min_candidates=3")
    assert resp.status_code == 200
    data = resp.json()

    assert data["searchConfig"]["initialRadiusKm"] == 2.0
    assert data["searchConfig"]["currentRadiusKm"] == 2.0
    assert data["searchConfig"]["maxRadiusKm"] == 20.0
    assert data["searchConfig"]["expansionCount"] == 0
    assert "initial 2.0km radius" in data["searchConfig"]["expansionReason"]

    donor_ids = [d["id"] for d in data["donors"]]
    assert len(donor_ids) == 3
    assert "D-CBE-01" in donor_ids
    assert "D-CBE-02" in donor_ids
    assert "D-CBE-03" in donor_ids
    assert "D-CBE-FAR" not in donor_ids  # Far donor must be excluded!


def test_radius_expansion_to_5km_when_2km_insufficient(client, coimbatore_setup, db):
    """
    When only 1 donor is within 2 km, search must progressively expand to 5 km.
    """
    # 1 donor in 2 km
    d1 = Donor(id="D-CBE-NEAR", blood_group="O-", eligibility="eligible", status="available", lat=11.0520, lng=77.0310) # ~0.57 km
    # 2 donors in 5 km ring (~3.2 km, e.g. Hopes College)
    d2 = Donor(id="D-CBE-HOP1", blood_group="O-", eligibility="eligible", status="available", lat=11.0350, lng=77.0120) # ~3.3 km
    d3 = Donor(id="D-CBE-HOP2", blood_group="O-", eligibility="eligible", status="available", lat=11.0380, lng=77.0150) # ~2.9 km
    # 1 donor in 15 km
    d4 = Donor(id="D-CBE-FAR", blood_group="O-", eligibility="eligible", status="available", lat=11.0247, lng=77.1264) # ~10.5 km (Sulur)
    db.add_all([d1, d2, d3, d4])
    db.commit()

    resp = client.get("/api/v1/blood/donors/ranked?emergencyId=BL-CBE-TRAUMA&min_candidates=3")
    assert resp.status_code == 200
    data = resp.json()

    assert data["searchConfig"]["currentRadiusKm"] == 5.0
    assert data["searchConfig"]["expansionCount"] == 1
    assert "expanded from 2.0km to 5.0km" in data["searchConfig"]["expansionReason"]

    donor_ids = [d["id"] for d in data["donors"]]
    assert len(donor_ids) == 3
    assert "D-CBE-NEAR" in donor_ids
    assert "D-CBE-HOP1" in donor_ids
    assert "D-CBE-HOP2" in donor_ids
    assert "D-CBE-FAR" not in donor_ids  # Sulur donor (10.5 km) must be excluded!


def test_radius_expansion_to_10km_when_5km_insufficient(client, coimbatore_setup, db):
    """
    When 2 km and 5 km have only 1 donor, search expands to 10 km.
    """
    # 1 donor at 1.5 km
    d1 = Donor(id="D-1", blood_group="O-", eligibility="eligible", status="available", lat=11.0500, lng=77.0300)
    # 2 donors at Gandhipuram (~8 km from KMCH)
    d2 = Donor(id="D-2", blood_group="O-", eligibility="eligible", status="available", lat=11.0180, lng=76.9680) # ~8.3 km
    d3 = Donor(id="D-3", blood_group="O-", eligibility="eligible", status="available", lat=11.0150, lng=76.9650) # ~8.7 km
    # 1 donor at 25 km (outside 20 km max)
    d_beyond = Donor(id="D-BEYOND", blood_group="O-", eligibility="eligible", status="available", lat=11.1500, lng=77.2500) # ~25 km
    db.add_all([d1, d2, d3, d_beyond])
    db.commit()

    resp = client.get("/api/v1/blood/donors/ranked?emergencyId=BL-CBE-TRAUMA&min_candidates=3")
    assert resp.status_code == 200
    data = resp.json()

    assert data["searchConfig"]["currentRadiusKm"] == 10.0
    assert data["searchConfig"]["expansionCount"] == 2
    assert "expanded from 5.0km to 10.0km" in data["searchConfig"]["expansionReason"]

    donor_ids = [d["id"] for d in data["donors"]]
    assert len(donor_ids) == 3
    assert "D-1" in donor_ids
    assert "D-2" in donor_ids
    assert "D-3" in donor_ids
    assert "D-BEYOND" not in donor_ids


def test_radius_expansion_to_20km_reaches_sulur(client, coimbatore_setup, db):
    """
    Sulur cluster is located ~10.5 km to 13 km east of KMCH along NH-544.
    If 2 km, 5 km, and 10 km lack donors, the progressive expansion must reach 20 km
    and successfully match the Sulur donor cluster.
    """
    # Sulur town donor at (11.0247, 77.1264) -> ~10.6 km from KMCH
    d_sulur_1 = Donor(id="D-SULUR-01", blood_group="O-", eligibility="eligible", status="available", lat=11.0247, lng=77.1264)
    # Sulur Air Force base area at (11.0150, 77.1500) -> ~13.4 km from KMCH
    d_sulur_2 = Donor(id="D-SULUR-02", blood_group="O-", eligibility="eligible", status="available", lat=11.0150, lng=77.1500)
    # Another donor at 18 km
    d_sulur_3 = Donor(id="D-SULUR-03", blood_group="O-", eligibility="eligible", status="available", lat=11.0000, lng=77.1800)
    # Donor beyond 20 km (e.g. Tiruppur outskirts at 32 km)
    d_tiruppur = Donor(id="D-TIRUPPUR", blood_group="O-", eligibility="eligible", status="available", lat=11.1085, lng=77.3411)
    db.add_all([d_sulur_1, d_sulur_2, d_sulur_3, d_tiruppur])
    db.commit()

    resp = client.get("/api/v1/blood/donors/ranked?emergencyId=BL-CBE-TRAUMA&min_candidates=3")
    assert resp.status_code == 200
    data = resp.json()

    assert data["searchConfig"]["currentRadiusKm"] == 20.0
    assert data["searchConfig"]["maxRadiusKm"] == 20.0
    assert data["searchConfig"]["expansionCount"] == 3
    assert "expanded from 10.0km to 20.0km" in data["searchConfig"]["expansionReason"]

    donor_ids = [d["id"] for d in data["donors"]]
    assert len(donor_ids) == 3
    assert "D-SULUR-01" in donor_ids
    assert "D-SULUR-02" in donor_ids
    assert "D-SULUR-03" in donor_ids
    assert "D-TIRUPPUR" not in donor_ids  # > 20 km must be excluded!


def test_no_suitable_donors_anywhere_within_20km(client, coimbatore_setup, db):
    """
    When no compatible eligible donors exist within 20 km,
    returns empty list with currentRadiusKm=20.0 and clear explanation.
    """
    # Only donor is 35 km away
    d_far = Donor(id="D-VERY-FAR", blood_group="O-", eligibility="eligible", status="available", lat=11.3000, lng=77.3000)
    db.add(d_far)
    db.commit()

    resp = client.get("/api/v1/blood/donors/ranked?emergencyId=BL-CBE-TRAUMA")
    assert resp.status_code == 200
    data = resp.json()

    assert data["donors"] == []
    assert data["searchConfig"]["currentRadiusKm"] == 20.0
    assert data["searchConfig"]["expansionCount"] == 3
    assert "No eligible compatible donors found" in data["searchConfig"]["expansionReason"]


def test_incompatible_blood_groups_never_qualify_in_expansion(client, coimbatore_setup, db):
    """Incompatible blood groups (e.g. AB+, B+, A+) must NEVER qualify even if right next to hospital."""
    d_incompat_1 = Donor(id="D-INCOMPAT-AB", blood_group="AB+", eligibility="eligible", status="available", lat=11.0558, lng=77.0345) # 0.0 km
    d_incompat_2 = Donor(id="D-INCOMPAT-B", blood_group="B+", eligibility="eligible", status="available", lat=11.0550, lng=77.0340) # 0.1 km
    db.add_all([d_incompat_1, d_incompat_2])
    db.commit()

    resp = client.get("/api/v1/blood/donors/ranked?emergencyId=BL-CBE-TRAUMA")
    assert resp.status_code == 200
    assert resp.json()["donors"] == []


def test_ineligible_and_unavailable_donors_never_qualify(client, coimbatore_setup, db):
    """Clinically deferred or unavailable donors must NEVER qualify regardless of proximity."""
    d_inelig = Donor(id="D-INELIG", blood_group="O-", eligibility="ineligible", status="available", lat=11.0558, lng=77.0345)
    d_unavail = Donor(id="D-UNAVAIL", blood_group="O-", eligibility="eligible", status="unavailable", lat=11.0558, lng=77.0345)
    db.add_all([d_inelig, d_unavail])
    db.commit()

    resp = client.get("/api/v1/blood/donors/ranked?emergencyId=BL-CBE-TRAUMA")
    assert resp.status_code == 200
    assert resp.json()["donors"] == []


def test_no_duplicate_donors_after_expansion(client, coimbatore_setup, db):
    """Expansions must not duplicate donors already included from earlier tiers."""
    d1 = Donor(id="D-TIER1", blood_group="O-", eligibility="eligible", status="available", lat=11.0520, lng=77.0310) # 0.57 km
    d2 = Donor(id="D-TIER2", blood_group="O-", eligibility="eligible", status="available", lat=11.0350, lng=77.0120) # 3.3 km
    d3 = Donor(id="D-TIER3", blood_group="O-", eligibility="eligible", status="available", lat=11.0180, lng=76.9680) # 8.3 km
    db.add_all([d1, d2, d3])
    db.commit()

    resp = client.get("/api/v1/blood/donors/ranked?emergencyId=BL-CBE-TRAUMA&min_candidates=3")
    assert resp.status_code == 200
    donors = resp.json()["donors"]
    donor_ids = [d["id"] for d in donors]

    assert len(donor_ids) == len(set(donor_ids)), "Duplicate donors detected in ranked output!"
    assert len(donor_ids) == 3


def test_missing_coordinates_handled_safely(client, coimbatore_setup, db):
    """
    Donors with missing coordinates are not counted as nearby within 2 km,
    do not fabricate distance, and are placed in unlocalizedDonors.
    """
    d_missing = Donor(id="D-NO-GEO", blood_group="O-", eligibility="eligible", status="available", lat=None, lng=None)
    db.add(d_missing)
    db.commit()

    resp = client.get("/api/v1/blood/donors/ranked?emergencyId=BL-CBE-TRAUMA")
    assert resp.status_code == 200
    data = resp.json()

    # The donor with missing coords must NOT be in the radius-matched donors
    assert not any(d["id"] == "D-NO-GEO" for d in data["donors"])

    # Must be in unlocalizedDonors
    assert data["unlocalizedDonors"] is not None
    unloc = next(d for d in data["unlocalizedDonors"] if d["id"] == "D-NO-GEO")
    assert unloc["distanceKm"] is None
    assert unloc["etaMinutes"] is None
    assert unloc["coordinates"] is None


def test_existing_endpoint_compatibility(client):
    """Confirms existing baseline query /api/v1/blood/donors/ranked?emergencyId=BL-102 works seamlessly."""
    resp = client.get("/api/v1/blood/donors/ranked?emergencyId=BL-102")
    assert resp.status_code == 200
    data = resp.json()
    assert "donors" in data
    assert "searchConfig" in data
    assert "aiRecommendation" in data
    assert data["searchConfig"]["initialRadiusKm"] == 2.0
    assert data["searchConfig"]["maxRadiusKm"] == 20.0
    assert len(data["donors"]) >= 1


def test_missing_emergency_404(client):
    """Confirms nonexistent emergency ID returns 404."""
    resp = client.get("/api/v1/blood/donors/ranked?emergencyId=NONEXISTENT-999")
    assert resp.status_code == 404
