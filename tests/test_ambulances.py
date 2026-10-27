from unittest.mock import patch
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.models.ambulance import Ambulance
from app.models.audit import AuditLog
from app.realtime.manager import ws_manager
from app.services.ambulance_service import AmbulanceService


def test_list_ambulances(client):
    response = client.get("/api/v1/ambulances")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 4


def test_get_ambulance_by_id(client):
    response = client.get("/api/v1/ambulances/amb-042")
    assert response.status_code == 200
    data = response.json()
    assert data["unitNumber"] == "AMB-042"
    assert "status" in data


def test_get_ambulance_routes(client):
    response = client.get("/api/v1/ambulances/amb-042/routes")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3
    route_b = next((r for r in data if r["label"] == "Route B"), None)
    assert route_b is not None
    assert route_b["isAiRecommended"] is True


def test_get_ambulance_location(client):
    response = client.get("/api/v1/ambulances/amb-042/location")
    assert response.status_code == 200
    data = response.json()
    assert data["ambulanceId"] == "amb-042"
    assert "currentLocation" in data


def test_get_ambulance_eta(client):
    response = client.get("/api/v1/ambulances/amb-042/eta")
    assert response.status_code == 200
    data = response.json()
    assert data["ambulanceId"] == "amb-042"
    assert "etaMinutes" in data


def test_update_ambulance_location_emits_telemetry(client, ambulance_token, db):
    """Verifies that updating ambulance location persists to DB and broadcasts ambulance.location_updated."""
    with client.websocket_connect(f"/ws?token={ambulance_token}") as ws:
        welcome = ws.receive_json()
        assert welcome["type"] == "connection.established"

        response = client.post(
            "/api/v1/ambulances/amb-042/location",
            headers={"Authorization": f"Bearer {ambulance_token}"},
            json={"lat": 12.966, "lng": 77.593, "heading": 90.0, "speedKmh": 55.0},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["currentLocation"]["lat"] == 12.966
        assert data["currentLocation"]["lng"] == 77.593
        assert data["speedKmh"] == 55.0

        # Verify WebSocket broadcast
        event = ws.receive_json()
        assert event["type"] == "ambulance.location_updated"
        payload = event["payload"]
        assert payload["ambulanceId"] == "amb-042"
        assert payload["unitNumber"] == "AMB-042"
        assert payload["currentLocation"]["lat"] == 12.966
        assert payload["currentLocation"]["lng"] == 77.593
        assert payload["currentLocation"]["heading"] == 90.0
        assert payload["speedKmh"] == 55.0

        # Verify DB persistence
        amb = db.query(Ambulance).filter(Ambulance.id == "amb-042").first()
        assert amb.lat == 12.966
        assert amb.lng == 77.593
        assert amb.speed_kmh == 55.0


def test_update_ambulance_status_emits_telemetry_and_audits(client, doctor_token, db):
    """Verifies that updating ambulance status persists to DB, logs collision-resistant audit, and broadcasts ambulance.status_updated."""
    with client.websocket_connect(f"/ws?token={doctor_token}") as ws:
        welcome = ws.receive_json()
        assert welcome["type"] == "connection.established"

        response = client.post(
            "/api/v1/ambulances/amb-042/status",
            headers={"Authorization": f"Bearer {doctor_token}"},
            json={"status": "transporting", "selectedRouteId": "route-fast-01"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "transporting"
        assert data["selectedRouteId"] == "route-fast-01"

        # Verify WebSocket broadcast
        event = ws.receive_json()
        assert event["type"] == "ambulance.status_updated"
        payload = event["payload"]
        assert payload["ambulanceId"] == "amb-042"
        assert payload["unitNumber"] == "AMB-042"
        assert payload["status"] == "transporting"
        assert payload["selectedRouteId"] == "route-fast-01"

        # Verify DB persistence
        amb = db.query(Ambulance).filter(Ambulance.id == "amb-042").first()
        assert amb.status == "transporting"
        assert amb.selected_route_id == "route-fast-01"

        # Verify audit record has collision-resistant UUID id
        audit = db.query(AuditLog).filter(
            AuditLog.resource_id == "amb-042",
            AuditLog.module == "ambulance",
        ).order_by(AuditLog.timestamp.desc()).first()
        assert audit is not None
        assert audit.id.startswith("audit-")
        assert len(audit.id) >= 16  # "audit-" + 10 hex chars = 16 chars min
        assert "transporting" in audit.action


def test_ambulance_telemetry_not_emitted_on_db_failure(client, ambulance_token):
    """Verifies that database failures roll back and do NOT emit success telemetry."""
    events_broadcast = []

    def mock_broadcast_sync(event):
        events_broadcast.append(event)

    with patch.object(ws_manager, "broadcast_sync", side_effect=mock_broadcast_sync):
        with patch("sqlalchemy.orm.Session.commit", side_effect=SQLAlchemyError("Simulated DB connection failure")):
            response = client.post(
                "/api/v1/ambulances/amb-042/location",
                headers={"Authorization": f"Bearer {ambulance_token}"},
                json={"lat": 12.980, "lng": 77.600},
            )
            assert response.status_code == 500
            assert len(events_broadcast) == 0


def test_ambulance_audit_ids_unique_across_rapid_updates(client, doctor_token, db):
    """Verifies that multiple status updates produce unique, collision-resistant audit IDs."""
    statuses = ["dispatched", "en_route", "on_scene", "transporting", "at_hospital"]
    audit_ids = []

    for s in statuses:
        res = client.post(
            "/api/v1/ambulances/amb-042/status",
            headers={"Authorization": f"Bearer {doctor_token}"},
            json={"status": s},
        )
        assert res.status_code == 200

    logs = db.query(AuditLog).filter(
        AuditLog.resource_id == "amb-042",
        AuditLog.module == "ambulance",
    ).all()

    audit_ids = [l.id for l in logs]
    assert len(audit_ids) >= len(statuses)
    # Collision check: every audit ID must be distinct
    assert len(audit_ids) == len(set(audit_ids))


def test_update_ambulance_unauthorized_roles(client, donor_token, patient_token):
    """Verifies that donors and patients are rejected from mutating ambulance location or status."""
    # Donor rejected
    r1 = client.post(
        "/api/v1/ambulances/amb-042/location",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"lat": 12.966, "lng": 77.593},
    )
    assert r1.status_code == 403

    r2 = client.post(
        "/api/v1/ambulances/amb-042/status",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"status": "idle"},
    )
    assert r2.status_code == 403

    # Patient rejected
    r3 = client.post(
        "/api/v1/ambulances/amb-042/location",
        headers={"Authorization": f"Bearer {patient_token}"},
        json={"lat": 12.966, "lng": 77.593},
    )
    assert r3.status_code == 403

    r4 = client.post(
        "/api/v1/ambulances/amb-042/status",
        headers={"Authorization": f"Bearer {patient_token}"},
        json={"status": "idle"},
    )
    assert r4.status_code == 403


def test_update_ambulance_invalid_status_rejected(client, doctor_token):
    """Verifies that unrecognized status values are rejected with 400 Bad Request."""
    response = client.post(
        "/api/v1/ambulances/amb-042/status",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"status": "flying"},
    )
    assert response.status_code == 400
    msg = response.json().get("message") or response.json().get("detail", "")
    assert "Invalid ambulance status" in msg


def test_update_ambulance_invalid_coordinates_rejected(client, ambulance_token):
    """Verifies that out-of-range GPS coordinates are rejected with 400 Bad Request."""
    response = client.post(
        "/api/v1/ambulances/amb-042/location",
        headers={"Authorization": f"Bearer {ambulance_token}"},
        json={"lat": 195.0, "lng": 77.593},
    )
    assert response.status_code == 400
    msg = response.json().get("message") or response.json().get("detail", "")
    assert "Invalid GPS coordinates" in msg


def test_update_ambulance_no_op_does_not_broadcast(client, ambulance_token):
    """Verifies that no-op telemetry updates (unchanged coordinates) avoid duplicate broadcasts."""
    events_broadcast = []

    def mock_broadcast_sync(event):
        events_broadcast.append(event)

    with patch.object(ws_manager, "broadcast_sync", side_effect=mock_broadcast_sync):
        # First update
        r1 = client.post(
            "/api/v1/ambulances/amb-042/location",
            headers={"Authorization": f"Bearer {ambulance_token}"},
            json={"lat": 12.950, "lng": 77.580, "heading": 45.0, "speedKmh": 40.0},
        )
        assert r1.status_code == 200
        assert len(events_broadcast) == 1

        # Second update with identical values (no-op)
        r2 = client.post(
            "/api/v1/ambulances/amb-042/location",
            headers={"Authorization": f"Bearer {ambulance_token}"},
            json={"lat": 12.950, "lng": 77.580, "heading": 45.0, "speedKmh": 40.0},
        )
        assert r2.status_code == 200
        # Broadcast count must remain 1
        assert len(events_broadcast) == 1
