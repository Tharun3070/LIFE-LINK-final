"""Tests for Geospatial & Route Intelligence Service."""
import pytest
from unittest.mock import patch, AsyncMock
import httpx
from app.geo.service import (
    GeospatialService,
    geospatial_service,
    calculate_haversine_distance,
    validate_coordinates,
)


def test_coordinate_validation():
    """Confirms out-of-bound latitudes and longitudes raise ValueError."""
    validate_coordinates(12.9716, 77.5946)  # Bangalore coordinates: valid
    validate_coordinates(-33.8688, 151.2093) # Sydney: valid

    with pytest.raises(ValueError, match="Latitude"):
        validate_coordinates(91.0, 77.0)

    with pytest.raises(ValueError, match="Longitude"):
        validate_coordinates(12.0, 181.0)


def test_haversine_formula_known_distance():
    """Tests Haversine calculation on known coordinates (e.g. Bangalore to Mysore ~128 km straight-line)."""
    bangalore = (12.9716, 77.5946)
    mysore = (12.2958, 76.6394)
    dist = calculate_haversine_distance(bangalore, mysore)
    assert 120.0 <= dist <= 140.0


@pytest.mark.asyncio
async def test_deterministic_fallback_distance_and_eta():
    """Unconfigured service provides safe deterministic road distance and ETA with truthful metadata."""
    service = GeospatialService(api_key="")
    origin = (12.9716, 77.5946)
    destination = (12.9352, 77.6245)

    res = await service.calculate_distance_and_eta(origin, destination)

    assert res["mode"] == "simulated_heuristic_fallback"
    assert res["is_live_traffic"] is False
    assert res["road_distance_km"] > 0
    assert res["haversine_distance_km"] > 0
    assert res["road_distance_km"] >= res["haversine_distance_km"]
    assert res["eta_minutes"] >= 1


@pytest.mark.asyncio
async def test_deterministic_fallback_multi_routes():
    """Unconfigured service computes Route A and Route B with transparent fallback tags."""
    service = GeospatialService(api_key="")
    origin = (12.9716, 77.5946)
    destination = (12.9352, 77.6245)

    routes = await service.get_multi_routes(origin, destination)

    assert len(routes) >= 2
    assert routes[0]["route_id"] == "route_A"
    assert routes[0]["is_recommended"] is True
    assert routes[0]["mode"] == "simulated_heuristic_fallback"
    assert routes[1]["route_id"] == "route_B"


@pytest.mark.asyncio
async def test_google_maps_distance_matrix_success():
    """Verifies parsing of Google Distance Matrix response when configured."""
    service = GeospatialService(api_key="mock_maps_key")

    mock_resp = {
        "status": "OK",
        "rows": [
            {
                "elements": [
                    {
                        "status": "OK",
                        "distance": {"value": 8500},  # 8.5 km
                        "duration": {"value": 1200},  # 20 min
                        "duration_in_traffic": {"value": 1380},  # 23 min
                    }
                ]
            }
        ],
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(status_code=200, json=mock_resp)
        res = await service.calculate_distance_and_eta((12.97, 77.59), (12.93, 77.62))

        assert res["mode"] == "google_maps_live"
        assert res["is_live_traffic"] is True
        assert res["road_distance_km"] == 8.5
        assert res["eta_minutes"] == 23


@pytest.mark.asyncio
async def test_google_maps_failure_graceful_fallback():
    """Verifies that Maps quota or server errors gracefully fall back without application crash."""
    service = GeospatialService(api_key="mock_maps_key")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(status_code=500, content=b"Internal Error")
        res = await service.calculate_distance_and_eta((12.97, 77.59), (12.93, 77.62))

        assert res["mode"] == "simulated_heuristic_fallback"
        assert res["is_live_traffic"] is False
        assert res["road_distance_km"] > 0


@pytest.mark.asyncio
async def test_proximity_ranking():
    """Ranks candidates by road distance."""
    origin = (12.9716, 77.5946)
    candidates = [
        {"id": "c1", "latitude": 13.05, "longitude": 77.60}, # Further
        {"id": "c2", "latitude": 12.98, "longitude": 77.59}, # Very close
    ]

    ranked = await geospatial_service.rank_candidates_by_proximity(origin, candidates)

    assert len(ranked) == 2
    assert ranked[0]["id"] == "c2"
    assert ranked[1]["id"] == "c1"
    assert ranked[0]["distance_km"] < ranked[1]["distance_km"]
