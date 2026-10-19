"""Tests for Priority 2: Live Ambulance GPS Telemetry Ingestion, Validation, and Persistence."""
from datetime import datetime, timezone, timedelta
import pytest
from app.models.ambulance import Ambulance
from app.models.user import User
from app.simulation.telemetry_simulator import generate_simulated_telemetry_packet, generate_simulated_telemetry_batch


def test_authenticated_telemetry_ingestion(client, ambulance_token, db):
    """Ambulance operator successfully ingests genuine GPS telemetry."""
    amb = db.query(Ambulance).first()
    assert amb is not None

    now = datetime.now(timezone.utc)
    payload = {
        "ambulanceId": amb.id,
        "deviceId": "DEVICE-GPS-4091",
        "lat": 12.9716,
        "lng": 77.5946,
        "heading": 180.0,
        "speedKmh": 45.5,
        "altitudeMeters": 915.2,
        "deviceTimestamp": now.isoformat(),
        "telemetrySource": "live_gps",
    }

    response = client.post(
        "/api/v1/ambulances/telemetry/ingest",
        json=payload,
        headers={"Authorization": f"Bearer {ambulance_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert data["ambulanceId"] == amb.id
    assert data["telemetrySource"] == "live_gps"
    assert data["isDuplicate"] is False

    # Verify DB persistence
    db.refresh(amb)
    assert amb.lat == 12.9716
    assert amb.lng == 77.5946
    assert amb.speed_kmh == 45.5
    assert amb.heading == 180.0
    assert amb.telemetry_source == "live_gps"
    assert amb.device_id == "DEVICE-GPS-4091"


def test_unauthorized_telemetry_rejection(client, patient_token, donor_token, db):
    """Patients and donors are forbidden from ingesting telemetry (403), unauthenticated rejected (401)."""
    amb = db.query(Ambulance).first()
    assert amb is not None

    payload = {
        "ambulanceId": amb.id,
        "deviceId": "UNAUTHORIZED-DEV",
        "lat": 12.97,
        "lng": 77.59,
        "deviceTimestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Patient rejected
    resp_pat = client.post(
        "/api/v1/ambulances/telemetry/ingest",
        json=payload,
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert resp_pat.status_code == 403

    # Donor rejected
    resp_donor = client.post(
        "/api/v1/ambulances/telemetry/ingest",
        json=payload,
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert resp_donor.status_code == 403

    # No token rejected
    resp_anon = client.post("/api/v1/ambulances/telemetry/ingest", json=payload)
    assert resp_anon.status_code == 401


def test_coordinate_bounds_validation(client, ambulance_token, db):
    """Invalid latitude or longitude coordinates are rejected."""
    amb = db.query(Ambulance).first()
    assert amb is not None

    # Invalid latitude (> 90.0)
    resp = client.post(
        "/api/v1/ambulances/telemetry/ingest",
        json={
            "ambulanceId": amb.id,
            "deviceId": "DEVICE-001",
            "lat": 95.0, # Out of range
            "lng": 77.59,
            "deviceTimestamp": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Authorization": f"Bearer {ambulance_token}"},
    )
    assert resp.status_code in [400, 422]


def test_stale_and_future_timestamp_validation(client, ambulance_token, db):
    """Timestamps too far in the future or stale (>24h) are rejected."""
    amb = db.query(Ambulance).first()
    assert amb is not None
    now = datetime.now(timezone.utc)

    # Future timestamp (> 5 minutes in future)
    future_time = now + timedelta(minutes=15)
    resp_future = client.post(
        "/api/v1/ambulances/telemetry/ingest",
        json={
            "ambulanceId": amb.id,
            "deviceId": "DEVICE-001",
            "lat": 12.97,
            "lng": 77.59,
            "deviceTimestamp": future_time.isoformat(),
        },
        headers={"Authorization": f"Bearer {ambulance_token}"},
    )
    assert resp_future.status_code == 400
    msg_future = resp_future.json().get("message") or resp_future.json().get("detail", "")
    assert "future" in msg_future.lower()

    # Stale timestamp (> 24 hours ago)
    stale_time = now - timedelta(hours=30)
    resp_stale = client.post(
        "/api/v1/ambulances/telemetry/ingest",
        json={
            "ambulanceId": amb.id,
            "deviceId": "DEVICE-001",
            "lat": 12.97,
            "lng": 77.59,
            "deviceTimestamp": stale_time.isoformat(),
        },
        headers={"Authorization": f"Bearer {ambulance_token}"},
    )
    assert resp_stale.status_code == 400
    msg_stale = resp_stale.json().get("message") or resp_stale.json().get("detail", "")
    assert "stale" in msg_stale.lower()


def test_out_of_order_and_duplicate_telemetry(client, ambulance_token, db):
    """Duplicate telemetry is acknowledged without error; out-of-order telemetry with different coordinates is rejected."""
    amb = db.query(Ambulance).first()
    assert amb is not None
    t0 = datetime.now(timezone.utc) - timedelta(minutes=2)

    # First update
    resp1 = client.post(
        "/api/v1/ambulances/telemetry/ingest",
        json={
            "ambulanceId": amb.id,
            "deviceId": "DEVICE-001",
            "lat": 12.95,
            "lng": 77.60,
            "heading": 90.0,
            "speedKmh": 40.0,
            "deviceTimestamp": t0.isoformat(),
        },
        headers={"Authorization": f"Bearer {ambulance_token}"},
    )
    assert resp1.status_code == 200

    # Duplicate update (same coords, timestamp <= last_dt)
    resp_dup = client.post(
        "/api/v1/ambulances/telemetry/ingest",
        json={
            "ambulanceId": amb.id,
            "deviceId": "DEVICE-001",
            "lat": 12.95,
            "lng": 77.60,
            "heading": 90.0,
            "speedKmh": 40.0,
            "deviceTimestamp": t0.isoformat(),
        },
        headers={"Authorization": f"Bearer {ambulance_token}"},
    )
    assert resp_dup.status_code == 200
    assert resp_dup.json()["isDuplicate"] is True

    # Out of order with different coordinates
    earlier_time = t0 - timedelta(seconds=30)
    resp_ooo = client.post(
        "/api/v1/ambulances/telemetry/ingest",
        json={
            "ambulanceId": amb.id,
            "deviceId": "DEVICE-001",
            "lat": 12.80, # Different coords
            "lng": 77.50,
            "deviceTimestamp": earlier_time.isoformat(),
        },
        headers={"Authorization": f"Bearer {ambulance_token}"},
    )
    assert resp_ooo.status_code == 400
    msg_ooo = resp_ooo.json().get("message") or resp_ooo.json().get("detail", "")
    assert "out-of-order" in msg_ooo.lower()


def test_implausible_coordinate_jump_rejected(client, ambulance_token, db):
    """A sudden coordinate jump exceeding vehicle physical limits (e.g. 500 km in 5 seconds) is rejected."""
    amb = db.query(Ambulance).first()
    assert amb is not None
    t0 = datetime.now(timezone.utc) - timedelta(minutes=1)

    # Initial valid position in Bengaluru
    client.post(
        "/api/v1/ambulances/telemetry/ingest",
        json={
            "ambulanceId": amb.id,
            "deviceId": "DEVICE-001",
            "lat": 12.9716,
            "lng": 77.5946,
            "deviceTimestamp": t0.isoformat(),
        },
        headers={"Authorization": f"Bearer {ambulance_token}"},
    )

    # Position 5 seconds later in Mumbai (lat 19.0760, lng 72.8777, ~850 km away!)
    t1 = t0 + timedelta(seconds=5)
    jump_resp = client.post(
        "/api/v1/ambulances/telemetry/ingest",
        json={
            "ambulanceId": amb.id,
            "deviceId": "DEVICE-001",
            "lat": 19.0760,
            "lng": 72.8777,
            "deviceTimestamp": t1.isoformat(),
        },
        headers={"Authorization": f"Bearer {ambulance_token}"},
    )
    assert jump_resp.status_code == 400
    msg_jump = jump_resp.json().get("message") or jump_resp.json().get("detail", "")
    assert "implausible coordinate jump" in msg_jump.lower()


def test_telemetry_simulator_integration(client, ambulance_token, db):
    """Simulator generates telemetry tagged as 'simulated' and persists with proper provenance."""
    amb = db.query(Ambulance).first()
    assert amb is not None

    packet = generate_simulated_telemetry_packet(ambulance_id=amb.id, step_index=1)
    assert packet.telemetrySource == "simulated"

    response = client.post(
        "/api/v1/ambulances/telemetry/ingest",
        json=packet.model_dump(),
        headers={"Authorization": f"Bearer {ambulance_token}"},
    )
    assert response.status_code == 200
    assert response.json()["telemetrySource"] == "simulated"

    # Verify ambulance response indicates simulated telemetry
    amb_resp = client.get(f"/api/v1/ambulances/{amb.id}")
    assert amb_resp.status_code == 200
    assert amb_resp.json()["telemetrySource"] == "simulated"


def test_operator_manual_update_fallback(client, ambulance_token, db):
    """The existing operator manual update workflow is preserved as a fallback."""
    amb = db.query(Ambulance).first()
    assert amb is not None

    response = client.post(
        f"/api/v1/ambulances/{amb.id}/location",
        json={"lat": 12.9800, "lng": 77.6000, "speedKmh": 25.0},
        headers={"Authorization": f"Bearer {ambulance_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["telemetrySource"] == "operator_manual"
    assert data["currentLocation"]["lat"] == 12.9800


def test_alembic_migration_0005_upgrade_downgrade(tmp_path):
    """Test Alembic upgrade to head (0005) and downgrade on an isolated database."""
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import create_engine, inspect

    db_path = tmp_path / "test_migration_0005_isolated.db"
    db_url = f"sqlite:///{db_path}"

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)

    # Run upgrade to head
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns("ambulances")]
    assert "telemetry_source" in columns
    assert "last_telemetry_at" in columns
    assert "device_id" in columns

    # Downgrade 1 revision (reverts 0005 to 0004)
    command.downgrade(cfg, "-1")

    engine.dispose()
    engine2 = create_engine(db_url)
    inspector2 = inspect(engine2)
    columns_after = [col["name"] for col in inspector2.get_columns("ambulances")]
    assert "telemetry_source" not in columns_after
    engine2.dispose()
