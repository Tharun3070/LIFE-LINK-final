"""
Live PostgreSQL Integration Verification Suite for LifeLink (Priority 4).

This test suite executes against an isolated, disposable PostgreSQL test instance
specified by the LIFELINK_POSTGRES_TEST_URL environment variable.

SAFETY CONTROLS:
- If LIFELINK_POSTGRES_TEST_URL is not set, all tests in this module are cleanly skipped.
- When set, the target is strictly verified via verify_isolated_postgresql_test_target:
  * Dialect MUST be postgresql (or postgresql+psycopg).
  * Database name MUST contain a test identifier ('test', 'disposable', 'sandbox', 'ci').
  * Protected production, canonical SQLite, or legacy databases are strictly rejected.
- Twilio live sending remains disabled (MOCK_NOTIFICATIONS_ONLY=True).
"""
import os
import time
from datetime import datetime, timezone
import pytest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import IntegrityError
from fastapi.testclient import TestClient

from app.core.config import settings, verify_isolated_postgresql_test_target
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.models.hospital import Hospital
from app.models.emergency import Emergency, EmergencyEvent
from app.models.ambulance import Ambulance
from app.models.donor import Donor
from app.models.consent import Consent
from app.models.interaction import DonorEmergencyInteraction
from app.core.security import create_access_token, get_password_hash


# Determine test database target from environment
PG_TEST_URL = os.environ.get("LIFELINK_POSTGRES_TEST_URL") or os.environ.get("POSTGRES_TEST_DATABASE_URL")

# Skip entire module if no live PostgreSQL URL is configured
pytestmark = pytest.mark.skipif(
    not PG_TEST_URL,
    reason="LIFELINK_POSTGRES_TEST_URL is not configured; skipping live PostgreSQL integration tests."
)


@pytest.fixture(scope="module")
def pg_target_info():
    """Validates the target PostgreSQL database against safety guards."""
    if not PG_TEST_URL:
        pytest.skip("LIFELINK_POSTGRES_TEST_URL not set")
    info = verify_isolated_postgresql_test_target(PG_TEST_URL)
    return info


@pytest.fixture(scope="module")
def pg_engine(pg_target_info):
    """Initializes a production-grade connection pool engine against the isolated PostgreSQL test DB."""
    normalized_url = settings.normalize_database_url(PG_TEST_URL)
    os.environ["DATABASE_URL"] = normalized_url
    settings.DATABASE_URL = normalized_url
    engine = create_engine(
        normalized_url,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=5,
        pool_timeout=15,
        pool_recycle=300,
        pool_pre_ping=True,
    )

    # Verify basic network reachability
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.fail(f"Could not connect to verified PostgreSQL test database {pg_target_info['sanitized_target']}: {exc}")

    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def pg_session_factory(pg_engine):
    """Yields a sessionmaker bound to the PostgreSQL test engine."""
    return sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)


@pytest.fixture(scope="function")
def pg_session(pg_engine, pg_session_factory):
    """Provides a transactional database session against the disposable PostgreSQL database."""
    session = pg_session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def pg_client(pg_session_factory):
    """FastAPI TestClient with database dependency overridden to the isolated PostgreSQL database."""
    def override_get_db():
        session = pg_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ==============================================================================
# INTEGRATION TESTS
# ==============================================================================

def test_01_pg_alembic_clean_migration_chain(pg_engine, pg_target_info):
    """Runs complete Alembic migration chain (0001 -> 0005) against clean disposable PostgreSQL DB."""
    from alembic.config import Config
    from alembic import command

    # Ensure disposable database is clean to test the complete migration chain from scratch
    Base.metadata.drop_all(bind=pg_engine)
    with pg_engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE;"))
        conn.commit()

    ini_path = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
    alembic_cfg = Config(os.path.abspath(ini_path) if os.path.exists(ini_path) else "alembic.ini")
    normalized_url = settings.normalize_database_url(PG_TEST_URL)
    alembic_cfg.set_main_option("sqlalchemy.url", normalized_url.replace("%", "%%"))

    # 1. Run migrations to head
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(pg_engine)
    tables = inspector.get_table_names()

    expected_tables = {
        "users", "hospitals", "consents", "donors", "emergencies",
        "organs", "ambulances", "audit_logs", "donor_emergency_interactions", "emergency_events"
    }
    for expected in expected_tables:
        assert expected in tables, f"Expected table '{expected}' not found in PostgreSQL test DB"

    # 2. Verify Alembic version in postgresql
    with pg_engine.connect() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert result == "0005_ambulance_telemetry_fields", f"Expected head revision 0005, got {result}"

    # 3. Verify emergencies.patient_id column and foreign key
    emg_cols = {c["name"]: c for c in inspector.get_columns("emergencies")}
    assert "patient_id" in emg_cols
    fks = inspector.get_foreign_keys("emergencies")
    patient_fk = next((fk for fk in fks if fk["constrained_columns"] == ["patient_id"]), None)
    assert patient_fk is not None
    assert patient_fk["referred_table"] == "users"

    # 4. Verify ambulances telemetry fields
    amb_cols = {c["name"]: c for c in inspector.get_columns("ambulances")}
    assert "telemetry_source" in amb_cols
    assert "last_telemetry_at" in amb_cols
    assert "device_id" in amb_cols

    # 5. Verify donors synthetic provenance fields
    donor_cols = {c["name"]: c for c in inspector.get_columns("donors")}
    assert "is_synthetic" in donor_cols
    assert "data_provenance" in donor_cols
    assert "simulated_coordinates" in donor_cols

    # 6. Test downgrade of migration 0005 (reverting to 0004)
    command.downgrade(alembic_cfg, "0004_patient_emergency_linkage")
    inspector_downgraded = inspect(pg_engine)
    amb_downgraded_cols = {c["name"] for c in inspector_downgraded.get_columns("ambulances")}
    assert "telemetry_source" not in amb_downgraded_cols

    # 7. Upgrade back to head
    command.upgrade(alembic_cfg, "head")
    inspector_reupgraded = inspect(pg_engine)
    amb_reupgraded_cols = {c["name"] for c in inspector_reupgraded.get_columns("ambulances")}
    assert "telemetry_source" in amb_reupgraded_cols


def test_02_pg_application_startup_and_health_readiness(pg_client):
    """Tests application health and readiness probe against live PostgreSQL database."""
    response = pg_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    ready_resp = pg_client.get("/health/ready")
    assert ready_resp.status_code == 200
    ready_data = ready_resp.json()
    assert ready_data["status"] == "ready"
    assert ready_data["database"] == "connected"


def test_03_pg_emergency_creation_and_patient_authorization(pg_session, pg_client):
    """Tests emergency creation, patient_id linkage, and cross-patient isolation in PostgreSQL."""
    # Seed baseline hospital
    hosp = Hospital(
        id="hosp-pg-001",
        name="Postgres General Hospital",
        address="100 PG Parkway",
        city="Bengaluru",
        lat=12.9716,
        lng=77.5946,
        type="general",
        blood_bank_available=True,
    )
    pg_session.merge(hosp)

    # Seed Doctor and Patients
    doc = User(
        id="usr-doc-pg",
        name="Dr. PG Doctor",
        email="doctor_pg@lifelink.test",
        hashed_password=get_password_hash("docpass123"),
        role="doctor",
        hospital_id=hosp.id,
    )
    patient1 = User(
        id="usr-pat-pg-1",
        name="Patient One",
        email="patient1_pg@lifelink.test",
        hashed_password=get_password_hash("patpass123"),
        role="patient",
    )
    patient2 = User(
        id="usr-pat-pg-2",
        name="Patient Two",
        email="patient2_pg@lifelink.test",
        hashed_password=get_password_hash("patpass123"),
        role="patient",
    )
    pg_session.merge(doc)
    pg_session.merge(patient1)
    pg_session.merge(patient2)
    pg_session.commit()

    # Clean up any leftover patient emergency from previous runs to ensure test isolation
    pg_session.query(Emergency).filter(Emergency.patient_id.in_([patient1.id, patient2.id])).delete(synchronize_session=False)
    pg_session.commit()

    doc_token = create_access_token(subject=doc.id, role=doc.role)
    pat1_token = create_access_token(subject=patient1.id, role=patient1.role)
    pat2_token = create_access_token(subject=patient2.id, role=patient2.role)

    # 1. Create emergency linked to patient1
    resp = pg_client.post(
        "/api/v1/emergencies",
        json={
            "type": "blood",
            "priority": "critical",
            "hospitalId": hosp.id,
            "hospitalName": hosp.name,
            "description": "Urgent transfusion needed",
            "bloodGroup": "O-",
            "unitsRequired": 2,
            "patientId": patient1.id,
        },
        headers={"Authorization": f"Bearer {doc_token}"},
    )
    assert resp.status_code == 200
    emg_data = resp.json()
    emg_id = emg_data["id"]
    assert emg_data["patientId"] == patient1.id

    # 2. Patient 1 accesses their own emergency
    me_resp = pg_client.get(
        "/api/v1/emergencies/patient/me",
        headers={"Authorization": f"Bearer {pat1_token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data is not None
    assert me_data["id"] == emg_id

    # 3. Patient 2 accesses /emergencies/patient/me and sees truthful standby (no emergency)
    pat2_me_resp = pg_client.get(
        "/api/v1/emergencies/patient/me",
        headers={"Authorization": f"Bearer {pat2_token}"},
    )
    assert pat2_me_resp.status_code == 200
    assert pat2_me_resp.json() is None


def test_04_pg_ambulance_telemetry_persistence(pg_session, pg_client):
    """Tests ambulance telemetry ingest and persistence in live PostgreSQL database."""
    now_iso = datetime.now(timezone.utc).isoformat()
    amb = Ambulance(
        id="amb-pg-001",
        unit_number="AMB-PG-001",
        status="en_route",
        driver_name="Operator PG",
        hospital_id="hosp-pg-001",
        lat=12.9500,
        lng=77.6000,
        heading=90.0,
        speed_kmh=45.0,
        telemetry_source="operator_manual",
        last_telemetry_at=None,
        updated_at=now_iso,
    )
    pg_session.merge(amb)
    pg_session.commit()

    amb_operator = User(
        id="usr-amb-pg",
        name="Paramedic Lead",
        email="ambulance_pg@lifelink.test",
        hashed_password=get_password_hash("ambpass123"),
        role="ambulance_operator",
        hospital_id="hosp-pg-001",
    )
    pg_session.merge(amb_operator)
    pg_session.commit()

    token = create_access_token(subject=amb_operator.id, role=amb_operator.role)

    # 1. Post genuine telemetry update through the GPS telemetry ingest endpoint
    ingest_response = pg_client.post(
        "/api/v1/ambulances/telemetry/ingest",
        json={
            "ambulanceId": amb.id,
            "deviceId": "GPS-UNIT-TEST-42",
            "lat": 12.9555,
            "lng": 77.6055,
            "heading": 95.0,
            "speedKmh": 52.0,
            "altitudeMeters": 910.0,
            "deviceTimestamp": now_iso,
            "telemetrySource": "live_gps",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ingest_response.status_code == 200
    ingest_data = ingest_response.json()
    assert ingest_data["status"] == "accepted"
    assert ingest_data["ambulanceId"] == amb.id
    assert ingest_data["telemetrySource"] == "live_gps"
    assert ingest_data["currentLocation"]["lat"] == 12.9555
    assert ingest_data["currentLocation"]["lng"] == 77.6055

    # Confirm telemetry fields persisted directly in PostgreSQL query
    pg_session.expire_all()
    queried_amb = pg_session.query(Ambulance).filter(Ambulance.id == amb.id).first()
    assert queried_amb.lat == 12.9555
    assert queried_amb.lng == 77.6055
    assert queried_amb.telemetry_source == "live_gps"
    assert queried_amb.device_id == "GPS-UNIT-TEST-42"

    # 2. Also verify operator manual location update endpoint preserves correct schema contract
    manual_response = pg_client.post(
        f"/api/v1/ambulances/{amb.id}/location",
        json={
            "lat": 12.9600,
            "lng": 77.6100,
            "heading": 100.0,
            "speedKmh": 48.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert manual_response.status_code == 200
    manual_data = manual_response.json()
    assert manual_data["currentLocation"]["lat"] == 12.9600
    assert manual_data["currentLocation"]["lng"] == 77.6100
    assert manual_data["telemetrySource"] == "operator_manual"

    pg_session.expire_all()
    queried_manual = pg_session.query(Ambulance).filter(Ambulance.id == amb.id).first()
    assert queried_manual.lat == 12.9600
    assert queried_manual.lng == 77.6100
    assert queried_manual.telemetry_source == "operator_manual"


def test_05_pg_transaction_rollback_and_post_commit_behavior(pg_session, pg_client):
    """Guarantees PostgreSQL atomic rollback on failed commit and suppresses WebSocket broadcast."""
    hosp = pg_session.query(Hospital).first()
    doc = pg_session.query(User).filter(User.role == "doctor").first()
    doc_token = create_access_token(subject=doc.id, role=doc.role)

    initial_count = pg_session.query(Emergency).count()

    with patch("app.realtime.manager.ws_manager.broadcast_sync") as mock_broadcast:
        with patch.object(Session, "commit", side_effect=RuntimeError("Simulated disk commit failure")):
            response = pg_client.post(
                "/api/v1/emergencies",
                json={
                    "type": "blood",
                    "priority": "critical",
                    "hospitalId": hosp.id,
                    "hospitalName": hosp.name,
                    "description": "Failing transaction test",
                    "bloodGroup": "A+",
                    "unitsRequired": 1,
                },
                headers={"Authorization": f"Bearer {doc_token}"},
            )
            assert response.status_code == 500

        # Verify WebSocket was NOT called on failed uncommitted transaction
        mock_broadcast.assert_not_called()

    # Verify no partial rows written in PostgreSQL
    pg_session.expire_all()
    final_count = pg_session.query(Emergency).count()
    assert final_count == initial_count

    # Verify positive post-commit behavior: successful commit triggers WebSocket broadcast
    with patch("app.realtime.manager.ws_manager.broadcast_sync") as mock_success_broadcast:
        success_resp = pg_client.post(
            "/api/v1/emergencies",
            json={
                "type": "blood",
                "priority": "critical",
                "hospitalId": hosp.id,
                "hospitalName": hosp.name,
                "description": "Successful commit broadcast test",
                "bloodGroup": "O+",
                "unitsRequired": 1,
            },
            headers={"Authorization": f"Bearer {doc_token}"},
        )
        assert success_resp.status_code == 200
        mock_success_broadcast.assert_called_once()


def test_06_pg_constraint_enforcement(pg_session):
    """Tests foreign key and unique constraint enforcement natively in PostgreSQL."""
    # Clean up test ambulances if present from prior runs to ensure idempotency
    pg_session.query(Ambulance).filter(Ambulance.id.in_(["amb-dup-1", "amb-dup-2"])).delete(synchronize_session=False)
    pg_session.commit()
    # 1. Foreign key violation: Non-existent hospital_id
    invalid_emergency = Emergency(
        id="emg-fk-viol",
        type="blood",
        priority="critical",
        status="created",
        hospital_id="non-existent-hosp-id",
        hospital_name="Ghost Hospital",
        created_at="2026-10-18T20:00:00Z",
        updated_at="2026-10-18T20:00:00Z",
        description="FK Violation Test",
    )
    pg_session.add(invalid_emergency)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

    # 2. Unique constraint violation: Duplicate ambulance unit_number
    amb1 = Ambulance(
        id="amb-dup-1",
        unit_number="AMB-UNIQUE-TEST",
        hospital_id="hosp-pg-001",
        updated_at="2026-10-18T20:00:00Z",
    )
    amb2 = Ambulance(
        id="amb-dup-2",
        unit_number="AMB-UNIQUE-TEST",
        hospital_id="hosp-pg-001",
        updated_at="2026-10-18T20:00:00Z",
    )
    pg_session.add(amb1)
    pg_session.commit()

    pg_session.add(amb2)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_07_pg_concurrent_writes_and_connection_cleanup(pg_session_factory, pg_engine):
    """Verifies that concurrent writes commit without deadlocks and connection pool releases connections."""
    with pg_session_factory() as cleanup_session:
        cleanup_session.query(Hospital).filter(Hospital.id.like("hosp-concur-%")).delete(synchronize_session=False)
        cleanup_session.commit()
    def worker_insert(worker_id: int):
        session = pg_session_factory()
        try:
            hosp = Hospital(
                id=f"hosp-concur-{worker_id}",
                name=f"Concurrent Hospital {worker_id}",
                address="Concurrent Road",
                city="Bengaluru",
                lat=12.9000 + (worker_id * 0.001),
                lng=77.5000 + (worker_id * 0.001),
                type="general",
            )
            session.add(hosp)
            session.commit()
            return True
        finally:
            session.close()

    # Execute 5 concurrent insertions
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker_insert, i) for i in range(5)]
        results = [f.result() for f in as_completed(futures)]

    assert all(results)

    # Verify connection pool state: all connections checked back in
    pool = pg_engine.pool
    assert pool.checkedout() == 0, f"Expected 0 checked out connections, got {pool.checkedout()}"


def test_08_pg_donor_emergency_interaction_integrity(pg_session):
    """Tests donor-emergency interaction lifecycle, provenance, and cascade in PostgreSQL."""
    donor = Donor(
        id="dnr-pg-001",
        blood_group="O-",
        distance_km=3.5,
        eta_minutes=10,
        eligibility="eligible",
        status="available",
        is_synthetic=True,
        data_provenance="test_fixture",
        simulated_coordinates=True,
    )
    emg = Emergency(
        id="emg-pg-int-001",
        type="blood",
        priority="critical",
        status="created",
        hospital_id="hosp-pg-001",
        hospital_name="Postgres General Hospital",
        created_at="2026-10-18T20:00:00Z",
        updated_at="2026-10-18T20:00:00Z",
        description="Interaction test emergency",
    )
    pg_session.merge(donor)
    pg_session.merge(emg)
    pg_session.commit()

    interaction = DonorEmergencyInteraction(
        id="dint-pg-001",
        emergency_id=emg.id,
        donor_id=donor.id,
        selected_at="2026-10-18T20:00:00Z",
        distance_km=3.5,
        eta_minutes=10,
        time_of_day_hours=14.5,
        day_of_week=6,
        emergency_priority="critical",
        compatibility_match_type="identical",
        donor_availability_at_selection="available",
        donor_total_previous_donations=4,
        contact_status="attempted",
        response_status="responded",
        acceptance_status="accepted",
        completion_status="completed",
        outcome_source="test_fixture",
        data_provenance="test_fixture",
        is_synthetic=True,
        created_at="2026-10-18T20:00:00Z",
        updated_at="2026-10-18T20:00:00Z",
    )
    pg_session.merge(interaction)
    pg_session.commit()

    # Query interaction
    queried = pg_session.query(DonorEmergencyInteraction).filter_by(id="dint-pg-001").first()
    assert queried is not None
    assert queried.is_synthetic is True
    assert queried.data_provenance == "test_fixture"
