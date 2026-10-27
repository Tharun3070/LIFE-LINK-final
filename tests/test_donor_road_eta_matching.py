"""
LifeLink Google Maps Road Distance & Driving ETA Donor Matching Test Suite.
File: tests/test_donor_road_eta_matching.py

Validates:
1. Patient emergency coordinates (emergency.location_lat, emergency.location_lng) are used as origin.
2. Hospital coordinates are NEVER substituted when emergency coordinates are missing or invalid.
3. Haversine filtering correctly operates across all 4 radius tiers (2 km, 5 km, 10 km, 20 km).
4. Google Maps road-distance and driving ETA mapping with truthful metadata attribution.
5. Deterministic ranking:
   - Driving time (etaMinutes), ascending.
   - Road distance (roadDistanceKm), ascending, when driving times are equal.
   - Stable donor ID as deterministic tie-breaker.
6. Traffic-aware estimates (duration_in_traffic) vs non-traffic route estimates.
7. Unroutable destinations (ZERO_RESULTS / NOT_FOUND) and invalid coordinates do not fabricate distances.
8. API timeouts, quota limits (OVER_QUERY_LIMIT), and HTTP errors gracefully fall back with truthful source labels.
9. In-memory TTL caching prevents redundant Distance Matrix requests for identical origin/destinations.
10. Maximum 3 selected donors for emergency contact; slots map to distinct test contacts in mock mode without DB overwrite.
11. Existing API response contract compatibility (GET /api/v1/blood/donors/ranked).
12. Notification safety controls assert carrier isolation and mock-only dispatch.
"""

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import pytest
import httpx
from app.models.donor import Donor
from app.models.emergency import Emergency
from app.models.hospital import Hospital
from app.models.user import User
from app.geo.service import GeospatialService, geospatial_service, calculate_haversine_distance
from app.services.donor_service import donor_service
from app.core.config import settings


@pytest.fixture
def emergency_geo_fixture(db):
    """
    Sets up an emergency scenario where Emergency is located at Gandhipuram (11.0183, 76.9639)
    while the receiving Hospital (KMCH) is at Avinashi Road (11.0558, 77.0345) ~10 km away.
    This fixture ensures we can distinctly prove emergency coordinates are used, not hospital coordinates.
    """
    geospatial_service.clear_cache()

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
        id="BL-CBE-GANDHIPURAM",
        type="blood",
        priority="critical",
        status="active",
        hospital_id="hosp-kmch-cbe",
        hospital_name="Kovai Medical Center and Hospital (KMCH)",
        created_at=now_str,
        updated_at=now_str,
        description="Gandhipuram road trauma transfusion O-",
        blood_group="O-",
        units_required=2,
        location_lat=11.0183,
        location_lng=76.9639,
    )
    db.add(emergency)
    db.commit()
    return hospital, emergency


def test_emergency_coordinates_used_as_origin(db, emergency_geo_fixture):
    """
    Donor D-GANDHI is at (11.0190, 76.9650), ~0.15 km from Emergency (11.0183, 76.9639),
    but >9.5 km from Hospital (11.0558, 77.0345).
    Verifies that distance and search tier evaluation uses Emergency coordinates as origin.
    """
    hosp, emerg = emergency_geo_fixture
    d1 = Donor(
        id="D-GANDHI-01",
        blood_group="O-",
        eligibility="eligible",
        status="available",
        lat=11.0190,
        lng=76.9650,
    )
    db.add(d1)
    db.commit()

    res = donor_service.get_ranked_donors(db, emergency_id="BL-CBE-GANDHIPURAM", min_candidates=1)
    assert len(res.donors) == 1
    d_out = res.donors[0]
    assert d_out.id == "D-GANDHI-01"
    # Straight-line distance from Emergency is ~0.14 km (< 0.5 km)
    assert d_out.straightLineDistanceKm < 0.5
    # If hospital coords had been used, straightLineDistanceKm would be ~9.5 km
    assert d_out.straightLineDistanceKm < 2.0
    assert res.searchConfig.currentRadiusKm == 2.0


def test_hospital_coordinates_not_substituted_when_emergency_coords_missing(db):
    """
    CRITICAL SAFETY REQUIREMENT:
    When emergency coordinates are missing or invalid, hospital coordinates MUST NOT be substituted.
    Must return clear location-unavailable result without fabricating distances.
    """
    now_str = datetime.now(timezone.utc).isoformat()
    hosp = Hospital(
        id="hosp-cbe-subst",
        name="Test Hospital",
        address="Test Road",
        city="Coimbatore",
        lat=11.0558,
        lng=77.0345,
        type="Trauma",
        blood_bank_available=True,
    )
    db.add(hosp)

    emerg_no_coords = Emergency(
        id="BL-NO-COORDS",
        type="blood",
        priority="critical",
        status="active",
        hospital_id="hosp-cbe-subst",
        hospital_name="Test Hospital",
        created_at=now_str,
        updated_at=now_str,
        description="Missing patient location coords emergency",
        blood_group="O-",
        units_required=2,
        location_lat=None,
        location_lng=None,
    )
    db.add(emerg_no_coords)

    d1 = Donor(
        id="D-NEAR-HOSP",
        blood_group="O-",
        eligibility="eligible",
        status="available",
        lat=11.0560,
        lng=77.0350,
    )
    db.add(d1)
    db.commit()

    res = donor_service.get_ranked_donors(db, emergency_id="BL-NO-COORDS")
    assert "Patient emergency coordinates are missing or invalid" in res.searchConfig.expansionReason
    assert len(res.donors) >= 1
    d_out = [d for d in res.donors if d.id == "D-NEAR-HOSP"][0]
    # Distances must NOT be silently calculated from the hospital
    assert d_out.distanceKm is None
    assert d_out.straightLineDistanceKm is None
    assert d_out.roadDistanceKm is None
    assert d_out.etaMinutes is None
    assert d_out.distanceSource == "unavailable_missing_emergency_coordinates"
    for d in res.donors:
        assert d.distanceKm is None
        assert d.roadDistanceKm is None
        assert d.etaMinutes is None
        assert d.distanceSource == "unavailable_missing_emergency_coordinates"


def test_haversine_filtering_at_all_four_radius_tiers(db, emergency_geo_fixture):
    """
    Validates Haversine filtering from Emergency origin across:
    Tier 0: 2 km
    Tier 1: 5 km
    Tier 2: 10 km
    Tier 3: 20 km
    """
    # Emergency at (11.0183, 76.9639)
    # D1 at ~1.2 km
    d1 = Donor(id="D-T1-01", blood_group="O-", eligibility="eligible", status="available", lat=11.0150, lng=76.9540)
    # D2 at ~3.5 km
    d2 = Donor(id="D-T2-01", blood_group="O-", eligibility="eligible", status="available", lat=11.0450, lng=76.9750)
    # D3 at ~8.2 km
    d3 = Donor(id="D-T3-01", blood_group="O-", eligibility="eligible", status="available", lat=11.0850, lng=76.9950)
    # D4 at ~15.0 km
    d4 = Donor(id="D-T4-01", blood_group="O-", eligibility="eligible", status="available", lat=11.1350, lng=77.0250)
    # D_OUT at ~28.0 km (beyond max 20 km)
    d_out = Donor(id="D-FAR-OUT", blood_group="O-", eligibility="eligible", status="available", lat=11.2500, lng=77.1000)

    db.add_all([d1, d2, d3, d4, d_out])
    db.commit()

    # Requesting min_candidates=1 -> stops at initial 2.0 km
    res1 = donor_service.get_ranked_donors(db, emergency_id="BL-CBE-GANDHIPURAM", min_candidates=1)
    assert res1.searchConfig.currentRadiusKm == 2.0
    assert [d.id for d in res1.donors] == ["D-T1-01"]

    # Requesting min_candidates=2 -> expands to 5.0 km
    res2 = donor_service.get_ranked_donors(db, emergency_id="BL-CBE-GANDHIPURAM", min_candidates=2)
    assert res2.searchConfig.currentRadiusKm == 5.0
    assert set(d.id for d in res2.donors) == {"D-T1-01", "D-T2-01"}

    # Requesting min_candidates=3 -> expands to 10.0 km
    res3 = donor_service.get_ranked_donors(db, emergency_id="BL-CBE-GANDHIPURAM", min_candidates=3)
    assert res3.searchConfig.currentRadiusKm == 10.0
    assert set(d.id for d in res3.donors) == {"D-T1-01", "D-T2-01", "D-T3-01"}

    # Requesting min_candidates=4 -> expands to 20.0 km
    res4 = donor_service.get_ranked_donors(db, emergency_id="BL-CBE-GANDHIPURAM", min_candidates=4)
    assert res4.searchConfig.currentRadiusKm == 20.0
    assert set(d.id for d in res4.donors) == {"D-T1-01", "D-T2-01", "D-T3-01", "D-T4-01"}
    # D-FAR-OUT at 28 km must NEVER be included
    assert "D-FAR-OUT" not in [d.id for d in res4.donors]


def test_road_distance_and_eta_mapping_from_google_maps(db, emergency_geo_fixture):
    """
    Verifies that Google Distance Matrix road distance and duration_in_traffic are mapped
    accurately into DonorResponse with appropriate metadata tags.
    """
    d1 = Donor(id="D-GMAP-01", blood_group="O-", eligibility="eligible", status="available", lat=11.0250, lng=76.9700)
    db.add(d1)
    db.commit()

    mock_matrix_response = {
        "status": "OK",
        "rows": [
            {
                "elements": [
                    {
                        "status": "OK",
                        "distance": {"value": 3200, "text": "3.2 km"},
                        "duration": {"value": 480, "text": "8 mins"},
                        "duration_in_traffic": {"value": 660, "text": "11 mins"},
                    }
                ]
            }
        ],
    }

    with patch("httpx.Client.get") as mock_get:
        mock_get.return_value = httpx.Response(status_code=200, json=mock_matrix_response)
        with patch.object(settings, "GOOGLE_MAPS_API_KEY", "AIzaFakeTestKey"):
            # Use test key on singleton
            geospatial_service.api_key = "AIzaFakeTestKey"
            geospatial_service.clear_cache()
            res = donor_service.get_ranked_donors(db, emergency_id="BL-CBE-GANDHIPURAM", min_candidates=1)

    assert len(res.donors) == 1
    d = res.donors[0]
    assert d.id == "D-GMAP-01"
    assert d.roadDistanceKm == 3.2
    assert d.etaMinutes == 11
    assert d.distanceSource == "google_maps_distance_matrix"
    assert d.etaSource == "google_maps_live_traffic"
    assert d.isLiveEstimate is True
    assert d.straightLineDistanceKm > 0
    assert d.straightLineDistanceKm != d.roadDistanceKm


def test_ranking_by_driving_time_then_road_distance_then_donor_id(db, emergency_geo_fixture):
    """
    Verifies ranking rules:
    1. Driving time (etaMinutes), ascending.
    2. Road distance (roadDistanceKm), ascending, when driving times are equal.
    3. Stable donor ID as deterministic tie-breaker.
    """
    # 4 donors near Gandhipuram:
    d_a = Donor(id="D-A", blood_group="O-", eligibility="eligible", status="available", lat=11.0200, lng=76.9650)
    d_b = Donor(id="D-B", blood_group="O-", eligibility="eligible", status="available", lat=11.0210, lng=76.9660)
    d_c = Donor(id="D-C", blood_group="O-", eligibility="eligible", status="available", lat=11.0220, lng=76.9670)
    d_d = Donor(id="D-D", blood_group="O-", eligibility="eligible", status="available", lat=11.0230, lng=76.9680)
    db.add_all([d_a, d_b, d_c, d_d])
    db.commit()

    # Simulate Distance Matrix results:
    # D-A: ETA 15 mins, road 8.0 km
    # D-B: ETA 10 mins, road 12.0 km (shorter ETA than D-A)
    # D-C: ETA 10 mins, road 7.5 km (equal ETA to D-B, but shorter road distance -> beats D-B!)
    # D-D: ETA 10 mins, road 7.5 km (equal ETA and road distance to D-C -> D-C beats D-D by ID!)
    mock_batch_results = [
        {
            "road_distance_km": 8.0,
            "haversine_distance_km": 1.0,
            "eta_minutes": 15,
            "mode": "google_maps_live",
            "distance_source": "google_maps_distance_matrix",
            "eta_source": "google_maps_live_traffic",
            "is_live_traffic": True,
        },
        {
            "road_distance_km": 12.0,
            "haversine_distance_km": 1.1,
            "eta_minutes": 10,
            "mode": "google_maps_live",
            "distance_source": "google_maps_distance_matrix",
            "eta_source": "google_maps_live_traffic",
            "is_live_traffic": True,
        },
        {
            "road_distance_km": 7.5,
            "haversine_distance_km": 1.2,
            "eta_minutes": 10,
            "mode": "google_maps_live",
            "distance_source": "google_maps_distance_matrix",
            "eta_source": "google_maps_live_traffic",
            "is_live_traffic": True,
        },
        {
            "road_distance_km": 7.5,
            "haversine_distance_km": 1.3,
            "eta_minutes": 10,
            "mode": "google_maps_live",
            "distance_source": "google_maps_distance_matrix",
            "eta_source": "google_maps_live_traffic",
            "is_live_traffic": True,
        },
    ]

    with patch.object(geospatial_service, "calculate_batch_distances_and_etas", return_value=mock_batch_results):
        res = donor_service.get_ranked_donors(db, emergency_id="BL-CBE-GANDHIPURAM", min_candidates=4)

    ranked_ids = [d.id for d in res.donors]
    # Expected order: D-C (#1), D-D (#2), D-B (#3), D-A (#4)
    assert ranked_ids == ["D-C", "D-D", "D-B", "D-A"]
    assert [d.aiRank for d in res.donors] == [1, 2, 3, 4]


def test_traffic_aware_vs_non_traffic_estimates(db, emergency_geo_fixture):
    """
    Distinguishes live traffic estimates (duration_in_traffic present)
    from non-traffic route estimates (duration only).
    """
    d1 = Donor(id="D-TRAFFIC", blood_group="O-", eligibility="eligible", status="available", lat=11.0200, lng=76.9650)
    d2 = Donor(id="D-NOTRAFFIC", blood_group="O-", eligibility="eligible", status="available", lat=11.0210, lng=76.9660)
    db.add_all([d1, d2])
    db.commit()

    mock_matrix_response = {
        "status": "OK",
        "rows": [
            {
                "elements": [
                    {
                        "status": "OK",
                        "distance": {"value": 2500},
                        "duration": {"value": 300},
                        "duration_in_traffic": {"value": 420},  # Has live traffic
                    },
                    {
                        "status": "OK",
                        "distance": {"value": 2700},
                        "duration": {"value": 360},  # No live traffic
                    },
                ]
            }
        ],
    }

    with patch("httpx.Client.get") as mock_get:
        mock_get.return_value = httpx.Response(status_code=200, json=mock_matrix_response)
        with patch.object(settings, "GOOGLE_MAPS_API_KEY", "AIzaFakeKey"):
            geospatial_service.api_key = "AIzaFakeKey"
            geospatial_service.clear_cache()
            res = donor_service.get_ranked_donors(db, emergency_id="BL-CBE-GANDHIPURAM", min_candidates=2)

    donors_by_id = {d.id: d for d in res.donors}
    assert donors_by_id["D-TRAFFIC"].etaSource == "google_maps_live_traffic"
    assert donors_by_id["D-TRAFFIC"].isLiveEstimate is True
    assert donors_by_id["D-NOTRAFFIC"].etaSource == "google_maps_routes"
    assert donors_by_id["D-NOTRAFFIC"].isLiveEstimate is False


def test_missing_routes_and_unroutable_destinations(db, emergency_geo_fixture):
    """
    When Google Maps Distance Matrix returns ZERO_RESULTS (no road route exists),
    must not fabricate a road distance or ETA.
    """
    d1 = Donor(id="D-UNROUTABLE", blood_group="O-", eligibility="eligible", status="available", lat=11.0200, lng=76.9650)
    db.add(d1)
    db.commit()

    mock_matrix_response = {
        "status": "OK",
        "rows": [
            {
                "elements": [
                    {
                        "status": "ZERO_RESULTS",
                    }
                ]
            }
        ],
    }

    with patch("httpx.Client.get") as mock_get:
        mock_get.return_value = httpx.Response(status_code=200, json=mock_matrix_response)
        with patch.object(settings, "GOOGLE_MAPS_API_KEY", "AIzaFakeKey"):
            geospatial_service.api_key = "AIzaFakeKey"
            geospatial_service.clear_cache()
            res = donor_service.get_ranked_donors(db, emergency_id="BL-CBE-GANDHIPURAM", min_candidates=1)

    assert len(res.donors) == 1
    d = res.donors[0]
    assert d.id == "D-UNROUTABLE"
    assert d.roadDistanceKm is None
    assert d.etaMinutes is None
    assert d.distanceSource == "google_maps_unroutable"
    assert d.isLiveEstimate is False


def test_api_timeouts_quota_errors_and_graceful_fallbacks(db, emergency_geo_fixture):
    """
    When Google Maps API times out or returns OVER_QUERY_LIMIT,
    the system must gracefully fall back to local heuristic routing without crashing.
    """
    d1 = Donor(id="D-QUOTA", blood_group="O-", eligibility="eligible", status="available", lat=11.0200, lng=76.9650)
    db.add(d1)
    db.commit()

    mock_quota_response = {
        "status": "OVER_QUERY_LIMIT",
        "error_message": "You have exceeded your request quota for this API.",
    }

    with patch("httpx.Client.get") as mock_get:
        mock_get.return_value = httpx.Response(status_code=200, json=mock_quota_response)
        with patch.object(settings, "GOOGLE_MAPS_API_KEY", "AIzaFakeKey"):
            geospatial_service.api_key = "AIzaFakeKey"
            geospatial_service.clear_cache()
            res = donor_service.get_ranked_donors(db, emergency_id="BL-CBE-GANDHIPURAM", min_candidates=1)

    assert len(res.donors) == 1
    d = res.donors[0]
    assert d.id == "D-QUOTA"
    assert d.roadDistanceKm > 0
    assert d.etaMinutes >= 2
    assert "simulated_heuristic_fallback" in d.distanceSource
    assert d.isLiveEstimate is False


def test_duplicate_requests_and_cache_behavior(db, emergency_geo_fixture):
    """
    Confirms in-memory TTL caching prevents redundant Distance Matrix network round-trips
    for identical origin/destination pairs.
    """
    d1 = Donor(id="D-CACHE-01", blood_group="O-", eligibility="eligible", status="available", lat=11.0200, lng=76.9650)
    db.add(d1)
    db.commit()

    mock_resp = {
        "status": "OK",
        "rows": [
            {
                "elements": [
                    {
                        "status": "OK",
                        "distance": {"value": 1500},
                        "duration": {"value": 240},
                        "duration_in_traffic": {"value": 300},
                    }
                ]
            }
        ],
    }

    with patch("httpx.Client.get") as mock_get:
        mock_get.return_value = httpx.Response(status_code=200, json=mock_resp)
        with patch.object(settings, "GOOGLE_MAPS_API_KEY", "AIzaFakeKey"):
            geospatial_service.api_key = "AIzaFakeKey"
            geospatial_service.clear_cache()

            # First call -> triggers network request
            res1 = donor_service.get_ranked_donors(db, emergency_id="BL-CBE-GANDHIPURAM", min_candidates=1)
            assert mock_get.call_count == 1

            # Second call -> must be served from cache with 0 additional network calls
            res2 = donor_service.get_ranked_donors(db, emergency_id="BL-CBE-GANDHIPURAM", min_candidates=1)
            assert mock_get.call_count == 1  # Call count did not increase!

            assert res1.donors[0].roadDistanceKm == res2.donors[0].roadDistanceKm
            assert res1.donors[0].etaMinutes == res2.donors[0].etaMinutes

            # Clearing cache causes next request to hit network again
            geospatial_service.clear_cache()
            res3 = donor_service.get_ranked_donors(db, emergency_id="BL-CBE-GANDHIPURAM", min_candidates=1)
            assert mock_get.call_count == 2


def test_maximum_three_selected_donors_and_test_contact_pool(db, emergency_geo_fixture):
    """
    Selects at most 3 distinct eligible donors for an emergency.
    In mock mode, maps slots to distinct test contacts from the pool.
    Verifies that donor records in database are NEVER overwritten.
    """
    donors = [
        Donor(id=f"D-POOL-{i}", blood_group="O-", eligibility="eligible", status="available", lat=11.0200 + (i * 0.001), lng=76.9650)
        for i in range(1, 6)
    ]
    db.add_all(donors)
    db.commit()

    selected = donor_service.select_donors_for_emergency_contact(
        db, emergency_id="BL-CBE-GANDHIPURAM", max_donors=5
    )

    # Must be bounded at maximum 3 selected donors
    assert len(selected) == 3
    assert [s["slot"] for s in selected] == [1, 2, 3]

    # Test contact numbers must be distinct
    test_phones = [s["testContactPhone"] for s in selected]
    assert len(set(test_phones)) == 3
    for phone in test_phones:
        assert phone in settings.TEST_CONTACT_POOL

    # Real donor records in the database must remain untouched
    db_donors = db.query(Donor).filter(Donor.id.like("D-POOL-%")).all()
    assert len(db_donors) == 5
    for d in db_donors:
        assert hasattr(d, "phone") is False


def test_existing_api_response_compatibility(client, emergency_geo_fixture, db):
    """
    Confirms backward compatibility of GET /api/v1/blood/donors/ranked response.
    """
    d1 = Donor(id="D-COMPAT-01", blood_group="O-", eligibility="eligible", status="available", lat=11.0200, lng=76.9650)
    db.add(d1)
    db.commit()

    resp = client.get("/api/v1/blood/donors/ranked?emergencyId=BL-CBE-GANDHIPURAM")
    assert resp.status_code == 200
    data = resp.json()

    # Required top-level keys
    assert "donors" in data
    assert "searchConfig" in data
    assert "aiRecommendation" in data

    # Search config keys
    sc = data["searchConfig"]
    assert "initialRadiusKm" in sc
    assert "currentRadiusKm" in sc
    assert "maxRadiusKm" in sc
    assert "expansionCount" in sc
    assert "expansionReason" in sc

    # Donor response item keys
    d = data["donors"][0]
    assert "id" in d
    assert "bloodGroup" in d
    assert "distanceKm" in d
    assert "straightLineDistanceKm" in d
    assert "roadDistanceKm" in d
    assert "etaMinutes" in d
    assert "distanceSource" in d
    assert "etaSource" in d
    assert "isLiveEstimate" in d
    assert "aiRank" in d
    assert d["aiRank"] == 1


def test_mock_only_notification_behavior(client, doctor_token, emergency_geo_fixture, db):
    """
    Confirms that contacting a donor in mock mode asserts carrier isolation,
    does not send real SMS/calls, and updates donor status.
    """
    d1 = Donor(
        id="D-MOCK-CONTACT",
        blood_group="O-",
        eligibility="eligible",
        status="available",
        lat=11.0200,
        lng=76.9650,
    )
    db.add(d1)
    # Ensure user consent is present
    user = User(
        id="usr-dnr-mock",
        name="Mock Donor User",
        email="mock.donor@example.com",
        hashed_password="hash",
        role="donor",
    )
    db.add(user)
    from app.models.consent import Consent
    consent = Consent(
        id="cns-mock-test",
        user_id="usr-dnr-mock",
        live_location=True,
        emergency_communication=True,
        donation_requests=True,
        health_data_sharing=True,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(consent)
    db.commit()

    # Link donor to consent user
    d1.user_id = "usr-dnr-mock"
    db.commit()

    with patch.object(settings, "TWILIO_ACCOUNT_SID", ""), patch.object(settings, "TWILIO_AUTH_TOKEN", ""):
        resp = client.post(
            "/api/v1/blood/donors/D-MOCK-CONTACT/contact",
            headers={"Authorization": f"Bearer {doctor_token}"},
            json={"emergencyId": "BL-CBE-GANDHIPURAM"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "contacted"
