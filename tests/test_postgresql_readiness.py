"""Tests for Priority 4: Database Compatibility, Credential Redaction, Transaction Boundaries, and Concurrency."""
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session
from app.models.emergency import Emergency
from app.models.ambulance import Ambulance
from app.models.hospital import Hospital
from app.schemas.emergency import EmergencyCreate
from app.schemas.ambulance import AmbulanceLocationUpdate
from app.services.emergency_service import emergency_service
from app.services.ambulance_service import ambulance_service
from app.core.config import Settings


def test_database_url_credential_redaction():
    """Verify that PostgreSQL connection URLs containing secrets are sanitized before display."""
    test_settings = Settings(
        DATABASE_URL="postgresql+psycopg://lifelink_admin:ultra_secret_production_password_2026@rds.ap-south-1.amazonaws.com:5432/lifelink_prod"
    )
    info = test_settings.get_sanitized_database_info()
    assert "ultra_secret_production_password_2026" not in info["resolved_target"]
    assert "***" in info["resolved_target"] or "lifelink_admin@" in info["resolved_target"]
    assert info["dialect"] == "postgresql+psycopg"
    assert info["is_canonical"] is False


def test_atomic_emergency_transaction_rollback_on_failure(db, doctor_token, client):
    """When an exception occurs during emergency creation, the transaction rolls back cleanly."""
    initial_emergency_count = db.query(Emergency).count()

    hospital = db.query(Hospital).first()
    assert hospital is not None

    # Simulate database commit failure
    with patch.object(Session, "commit", side_effect=RuntimeError("Simulated disk I/O failure")):
        response = client.post(
            "/api/v1/emergencies",
            json={
                "type": "blood",
                "priority": "critical",
                "hospitalId": hospital.id,
                "hospitalName": hospital.name,
                "description": "Rollback test emergency",
                "bloodGroup": "O+",
                "unitsRequired": 2,
            },
            headers={"Authorization": f"Bearer {doctor_token}"},
        )
        assert response.status_code == 500

    # Verify no partial or orphaned emergency records exist
    db.expire_all()
    final_emergency_count = db.query(Emergency).count()
    assert final_emergency_count == initial_emergency_count


def test_failed_location_update_does_not_broadcast_websocket(db, ambulance_token, client):
    """If database persistence fails for ambulance location, no WebSocket event is broadcast."""
    amb = db.query(Ambulance).first()
    assert amb is not None
    original_lat = amb.lat

    with patch("app.services.ambulance_service.ws_manager.broadcast_sync") as mock_broadcast:
        with patch.object(Session, "commit", side_effect=RuntimeError("Simulated database failure")):
            response = client.post(
                f"/api/v1/ambulances/{amb.id}/location",
                json={"lat": 13.0500, "lng": 77.6500, "speedKmh": 50.0},
                headers={"Authorization": f"Bearer {ambulance_token}"},
            )
            assert response.status_code == 500

        # Verify that uncommitted location was NOT broadcast over WebSocket
        mock_broadcast.assert_not_called()

    # Verify database state remained unchanged
    db.expire_all()
    amb_after = db.query(Ambulance).filter(Ambulance.id == amb.id).first()
    assert amb_after.lat == original_lat


def test_alembic_all_migrations_sqlite_upgrade_downgrade(tmp_path):
    """Full migration chain (0001 -> 0005) tests upgrade to head and downgrade."""
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import create_engine, inspect

    db_path = tmp_path / "test_full_chain.db"
    db_url = f"sqlite:///{db_path}"

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)

    # 1. Upgrade full chain to head
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "users" in tables
    assert "emergencies" in tables
    assert "ambulances" in tables
    assert "donors" in tables
    assert "donor_emergency_interactions" in tables

    # Verify columns from migrations 0004 and 0005
    emg_cols = [c["name"] for c in inspector.get_columns("emergencies")]
    assert "patient_id" in emg_cols

    amb_cols = [c["name"] for c in inspector.get_columns("ambulances")]
    assert "telemetry_source" in amb_cols
    assert "last_telemetry_at" in amb_cols
    assert "device_id" in amb_cols

    # 2. Downgrade revisions down to 0004 to verify 0005 reversion
    command.downgrade(cfg, "0004_patient_emergency_linkage")
    engine.dispose()

    engine2 = create_engine(db_url)
    inspector2 = inspect(engine2)
    amb_cols_reverted = [c["name"] for c in inspector2.get_columns("ambulances")]
    assert "telemetry_source" not in amb_cols_reverted
    engine2.dispose()


def test_postgresql_url_driver_normalization():
    """Verify that postgres:// and postgresql:// are normalized to postgresql+psycopg://."""
    s1 = Settings(DATABASE_URL="postgres://user:pass@db.internal:5432/lifelink")
    assert s1.DATABASE_URL.startswith("postgresql+psycopg://")

    s2 = Settings(DATABASE_URL="postgresql://user:pass@db.internal:5432/lifelink")
    assert s2.DATABASE_URL.startswith("postgresql+psycopg://")


def test_postgresql_isolated_target_guard():
    """Verify that write tests refuse to execute against canonical or legacy databases."""
    canonical_settings = Settings()
    # The default DATABASE_URL resolves to canonical database
    info = canonical_settings.get_sanitized_database_info()
    if info["is_canonical"]:
        with pytest.raises(RuntimeError, match="PROTECTED DATABASE GUARD"):
            canonical_settings.assert_isolated_target_for_write_testing()


def test_postgresql_offline_alembic_ddl_generation():
    """Alembic offline mode generates valid PostgreSQL DDL with correct boolean and FK constraints."""
    from alembic.config import Config
    from alembic import command
    import io
    from contextlib import redirect_stdout

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://app_user:app_pass@localhost:5432/lifelink_test")

    buf = io.StringIO()
    with redirect_stdout(buf):
        command.upgrade(cfg, "head", sql=True)

    output = buf.getvalue()
    # Check that output generated SQL statements
    assert "CREATE TABLE emergencies" in output
    assert "ALTER TABLE emergencies ADD COLUMN patient_id" in output
    assert "fk_emergencies_patient_id_users" in output
    assert "ALTER TABLE ambulances ADD COLUMN telemetry_source" in output
    assert "ALTER TABLE donors ADD COLUMN is_synthetic BOOLEAN DEFAULT false" in output
    assert "0005_ambulance_telemetry_fields" in output


def test_postgresql_sqlalchemy_table_compilation():
    """All SQLAlchemy ORM models compile valid PostgreSQL DDL without dialect syntax errors."""
    from app.db.base import Base
    import app.models
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects import postgresql

    for table in Base.metadata.sorted_tables:
        sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert f"CREATE TABLE {table.name}" in sql
        assert len(sql) > 50


def test_alembic_config_escapes_percent_encoded_url():
    """Verify that Alembic configuration handles percent-encoded characters in connection URLs without interpolation errors."""
    from alembic.config import Config
    import io
    from contextlib import redirect_stdout
    from alembic import command

    cfg = Config("alembic.ini")
    raw_url = "postgresql+psycopg://user:pass%402026@localhost:5432/lifelink_test"
    # Escaping % as %% prevents ValueError: invalid interpolation syntax
    cfg.set_main_option("sqlalchemy.url", raw_url.replace("%", "%%"))

    buf = io.StringIO()
    with redirect_stdout(buf):
        command.upgrade(cfg, "head", sql=True)

    output = buf.getvalue()
    assert "CREATE TABLE emergencies" in output
    assert cfg.get_main_option("sqlalchemy.url") == raw_url

