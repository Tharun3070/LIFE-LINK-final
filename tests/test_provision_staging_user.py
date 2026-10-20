import sys
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.user import User
from app.models.consent import Consent
from app.models.audit import AuditLog
from app.core.security import verify_password
from scripts.provision_staging_user import (
    verify_staging_environment_guards,
    verify_staging_database_identity,
    verify_server_database_identity,
    get_staging_password,
    provision_staging_user,
    parse_arguments,
)


@pytest.fixture
def mock_isolated_db(monkeypatch):
    """Creates an isolated in-memory SQLite database sharing the same engine connection via StaticPool with foreign keys enforced."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    from sqlalchemy import event

    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(test_engine)
    TestingSession = sessionmaker(bind=test_engine)

    # Patch SessionLocal and engine in the provisioner
    monkeypatch.setattr("scripts.provision_staging_user.SessionLocal", TestingSession)
    monkeypatch.setattr("scripts.provision_staging_user.engine", test_engine)

    # Monkeypatch the environment guards and server identity verification for test db isolation
    monkeypatch.setattr(
        "scripts.provision_staging_user.verify_staging_environment_guards",
        lambda expected_db_name=None, expected_db_host=None: {
            "verified": True,
            "database": "test_db",
            "host": "localhost",
            "port": 5432,
        },
    )
    monkeypatch.setattr(
        "scripts.provision_staging_user.verify_server_database_identity",
        lambda db, expected_db_name: expected_db_name or "test_db",
    )

    yield TestingSession
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


def test_sqlite_sessions_share_same_database_via_static_pool(mock_isolated_db):
    """Verifies that separate sessions created from mock_isolated_db share the exact same in-memory DB."""
    session1 = mock_isolated_db()
    session2 = mock_isolated_db()

    user = User(
        id="usr-pool-test",
        name="Pool Test",
        email="pool@test.internal",
        hashed_password="hash",
        role="doctor",
        is_verified=True,
    )
    session1.add(user)
    session1.commit()

    # Session 2 must be able to read the row committed in Session 1
    found = session2.query(User).filter(User.id == "usr-pool-test").first()
    assert found is not None
    assert found.email == "pool@test.internal"

    session1.close()
    session2.close()


def test_guard_fails_when_app_env_not_staging(monkeypatch):
    """Ensures provisioner strictly fails closed when APP_ENV is development or production."""
    monkeypatch.setattr("app.core.config.settings.APP_ENV", "development")
    with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Staging provisioning is restricted to APP_ENV='staging'"):
        verify_staging_environment_guards()


def test_guard_fails_when_dialect_not_postgresql(monkeypatch):
    """Ensures provisioner strictly refuses SQLite/non-Postgres targets."""
    monkeypatch.setattr("app.core.config.settings.APP_ENV", "staging")
    fake_engine = MagicMock()
    fake_engine.dialect.name = "sqlite"
    monkeypatch.setattr("scripts.provision_staging_user.engine", fake_engine)

    with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Staging provisioning requires a genuine PostgreSQL database"):
        verify_staging_environment_guards()


def test_cli_rejects_allow_test_db_bypass_flag(monkeypatch):
    """Verifies that the CLI cannot bypass guards and rejects --allow-test-db as unrecognized."""
    monkeypatch.setattr(sys, "argv", ["provision_staging_user.py", "--allow-test-db"])
    with pytest.raises(SystemExit):
        parse_arguments()


def test_password_policy_enforcement(monkeypatch):
    """Rejects passwords shorter than 8 characters."""
    monkeypatch.setenv("STAGING_USER_PASSWORD", "short")
    with pytest.raises(ValueError, match="Password policy: Staging test account password must be at least 8 characters"):
        get_staging_password("STAGING_USER_PASSWORD")


def test_dry_run_does_not_request_password_or_write(mock_isolated_db, monkeypatch):
    """Verifies that dry-run (omitting --confirm) performs no write and NEVER requests a password."""
    monkeypatch.delenv("STAGING_USER_PASSWORD", raising=False)

    mock_pwd_getter = MagicMock(side_effect=AssertionError("get_staging_password must not be called in dry-run!"))
    monkeypatch.setattr("scripts.provision_staging_user.get_staging_password", mock_pwd_getter)

    args = MagicMock()
    args.confirm = False
    args.email = "dryrun.doctor@lifelink.internal"
    args.name = "Dry Run Doctor"
    args.role = "doctor"
    args.role_title = "Attending Physician"
    args.user_id = "usr-dryrun-01"
    args.hospital_id = None
    args.password_env = "STAGING_USER_PASSWORD"
    args.expected_db_name = None
    args.expected_db_host = None

    result = provision_staging_user(args)

    assert result["status"] == "dry_run"
    assert result["created"] is False
    mock_pwd_getter.assert_not_called()

    # Verify zero records in DB
    db = mock_isolated_db()
    assert db.query(User).count() == 0
    assert db.query(Consent).count() == 0
    assert db.query(AuditLog).count() == 0
    db.close()


def test_idempotent_duplicate_check_does_not_request_password(mock_isolated_db, monkeypatch):
    """Verifies that when an account already exists, provisioner aborts idempotently without requesting password."""
    monkeypatch.setenv("STAGING_USER_PASSWORD", "SecureStagingPassword2026!")

    args = MagicMock()
    args.confirm = True
    args.email = "existing.user@lifelink.internal"
    args.name = "Existing User"
    args.role = "doctor"
    args.role_title = "Doctor"
    args.user_id = "usr-existing-01"
    args.hospital_id = None
    args.password_env = "STAGING_USER_PASSWORD"
    args.expected_db_name = None
    args.expected_db_host = None

    # First run creates the user
    res1 = provision_staging_user(args)
    assert res1["status"] == "created"

    # Now remove password and patch getter to assert it is never called
    monkeypatch.delenv("STAGING_USER_PASSWORD", raising=False)
    mock_pwd_getter = MagicMock(side_effect=AssertionError("get_staging_password must not be called for existing user!"))
    monkeypatch.setattr("scripts.provision_staging_user.get_staging_password", mock_pwd_getter)

    # Second run should return already_exists without requesting password
    res2 = provision_staging_user(args)
    assert res2["status"] == "already_exists"
    assert res2["created"] is False
    mock_pwd_getter.assert_not_called()

    db = mock_isolated_db()
    assert db.query(User).count() == 1
    db.close()


def test_confirmed_provisioning_creates_exact_records(mock_isolated_db, monkeypatch):
    """Verifies that running with --confirm creates exactly 1 User, 1 Consent, and 1 AuditLog."""
    monkeypatch.setenv("STAGING_USER_PASSWORD", "SecureStagingPassword2026!")

    args = MagicMock()
    args.confirm = True
    args.email = "staging.doctor@lifelink.internal"
    args.name = "Staging Emergency Doctor"
    args.role = "doctor"
    args.role_title = "Attending Emergency Physician"
    args.user_id = "usr-staging-doctor-01"
    args.hospital_id = None
    args.password_env = "STAGING_USER_PASSWORD"
    args.expected_db_name = None
    args.expected_db_host = None

    result = provision_staging_user(args)

    assert result["status"] == "created"
    assert result["created"] is True
    assert result["email"] == "staging.doctor@lifelink.internal"

    db = mock_isolated_db()
    # 1. Exactly 1 User
    users = db.query(User).all()
    assert len(users) == 1
    u = users[0]
    assert u.id == "usr-staging-doctor-01"
    assert u.email == "staging.doctor@lifelink.internal"
    assert u.role == "doctor"
    assert u.hospital_id is None
    assert u.is_verified is True
    assert verify_password("SecureStagingPassword2026!", u.hashed_password) is True

    # 2. Exactly 1 Consent — MUST be explicit opt-out (unconsented communication state)
    consents = db.query(Consent).all()
    assert len(consents) == 1
    c = consents[0]
    assert c.user_id == u.id
    assert c.emergency_communication is False
    assert c.donation_requests is False
    assert c.live_location is False
    assert c.health_data_sharing is False

    # 3. Exactly 1 AuditLog
    audits = db.query(AuditLog).all()
    assert len(audits) == 1
    assert audits[0].resource_id == u.id
    assert audits[0].actor == "staging-user-provisioner"
    assert audits[0].status == "success"
    assert "explicit communication opt-out" in audits[0].action

    db.close()


def test_consent_service_preserves_explicit_opt_out_without_silent_opt_in(mock_isolated_db, monkeypatch):
    """Proves that consent_service.get_user_consent does NOT silently grant opt-in consent to provisioned account."""
    from app.services.consent_service import consent_service

    monkeypatch.setenv("STAGING_USER_PASSWORD", "SecureStagingPassword2026!")
    args = MagicMock()
    args.confirm = True
    args.email = "optout.check@lifelink.internal"
    args.name = "Opt Out Test User"
    args.role = "doctor"
    args.role_title = "Doctor"
    args.user_id = "usr-optout-01"
    args.hospital_id = None
    args.password_env = "STAGING_USER_PASSWORD"
    args.expected_db_name = None
    args.expected_db_host = None

    provision_staging_user(args)

    db = mock_isolated_db()
    # Query consent through ConsentService (simulating first frontend access)
    consent_dto = consent_service.get_user_consent(db, "usr-optout-01")

    # Consent MUST remain strictly opted-out
    assert consent_dto.emergencyCommunication is False
    assert consent_dto.donationRequests is False
    assert consent_dto.liveLocation is False
    assert consent_dto.healthDataSharing is False

    # Communication authorization check in donor_service / interaction_service logic:
    # has_consent = bool(consent and consent.emergency_communication)
    consent_record = db.query(Consent).filter(Consent.user_id == "usr-optout-01").first()
    assert bool(consent_record and consent_record.emergency_communication) is False

    db.close()


def test_idempotent_duplicate_check_prevents_duplicate_user(mock_isolated_db, monkeypatch):
    """Verifies that running provisioner a second time with existing user is safe and idempotent."""
    monkeypatch.setenv("STAGING_USER_PASSWORD", "SecureStagingPassword2026!")

    args = MagicMock()
    args.confirm = True
    args.email = "idempotent.user@lifelink.internal"
    args.name = "Test User"
    args.role = "doctor"
    args.role_title = "Doctor"
    args.user_id = "usr-idempotent-01"
    args.hospital_id = None
    args.password_env = "STAGING_USER_PASSWORD"
    args.expected_db_name = None
    args.expected_db_host = None

    # First run: creates
    res1 = provision_staging_user(args)
    assert res1["status"] == "created"

    # Second run: detects existing and aborts
    res2 = provision_staging_user(args)
    assert res2["status"] == "already_exists"
    assert res2["created"] is False

    db = mock_isolated_db()
    assert db.query(User).count() == 1
    db.close()


def test_rollback_on_database_error(mock_isolated_db, monkeypatch):
    """Verifies that an error during commit triggers rollback and closes session cleanly."""
    monkeypatch.setenv("STAGING_USER_PASSWORD", "SecureStagingPassword2026!")

    args = MagicMock()
    args.confirm = True
    args.email = "rollback.doctor@lifelink.internal"
    args.name = "Rollback Doctor"
    args.role = "doctor"
    args.role_title = "Doctor"
    args.user_id = "usr-rollback-01"
    args.hospital_id = None
    args.password_env = "STAGING_USER_PASSWORD"
    args.expected_db_name = None
    args.expected_db_host = None

    real_session_maker = mock_isolated_db

    def failing_session(*s_args, **s_kwargs):
        session = real_session_maker(*s_args, **s_kwargs)
        monkeypatch.setattr(session, "commit", MagicMock(side_effect=RuntimeError("Simulated write failure")))
        return session

    monkeypatch.setattr("scripts.provision_staging_user.SessionLocal", failing_session)

    with pytest.raises(RuntimeError, match="Simulated write failure"):
        provision_staging_user(args)

    # Verify no records committed in the DB
    db = real_session_maker()
    assert db.query(User).filter(User.id == "usr-rollback-01").first() is None
    assert db.query(Consent).count() == 0
    assert db.query(AuditLog).count() == 0
    db.close()


def test_provisioning_foreign_key_ordering_with_sqlite_enforcement(mock_isolated_db, monkeypatch):
    """
    Regression test: Verifies that User is flushed to the database prior to
    Consent insertion under strict SQLite PRAGMA foreign_keys=ON enforcement,
    preventing Foreign Key violation on consents_user_id_fkey.
    """
    monkeypatch.setenv("STAGING_USER_PASSWORD", "SecureStagingPassword2026!")

    args = MagicMock()
    args.confirm = True
    args.email = "fk.ordering@lifelink.internal"
    args.name = "FK Ordering Test"
    args.role = "doctor"
    args.role_title = "Doctor"
    args.user_id = "usr-fk-ordering-01"
    args.hospital_id = None
    args.password_env = "STAGING_USER_PASSWORD"
    args.expected_db_name = None
    args.expected_db_host = None

    result = provision_staging_user(args)
    assert result["status"] == "created"
    assert result["created"] is True

    db = mock_isolated_db()
    # Confirm exactly 1 User, 1 Consent, 1 AuditLog created
    user = db.query(User).filter(User.id == "usr-fk-ordering-01").first()
    assert user is not None
    consent = db.query(Consent).filter(Consent.user_id == "usr-fk-ordering-01").first()
    assert consent is not None
    assert consent.live_location is False
    assert consent.emergency_communication is False
    assert consent.donation_requests is False
    assert consent.health_data_sharing is False
    audit = db.query(AuditLog).filter(AuditLog.resource_id == "usr-fk-ordering-01").first()
    assert audit is not None
    db.close()


def test_rollback_on_flush_failure_leaves_no_records(mock_isolated_db, monkeypatch):
    """Verifies that an error during flush triggers rollback and leaves zero records in database."""
    monkeypatch.setenv("STAGING_USER_PASSWORD", "SecureStagingPassword2026!")

    args = MagicMock()
    args.confirm = True
    args.email = "flush.fail@lifelink.internal"
    args.name = "Flush Fail User"
    args.role = "doctor"
    args.role_title = "Doctor"
    args.user_id = "usr-flush-fail-01"
    args.hospital_id = None
    args.password_env = "STAGING_USER_PASSWORD"
    args.expected_db_name = None
    args.expected_db_host = None

    real_session_maker = mock_isolated_db

    def failing_flush_session(*s_args, **s_kwargs):
        session = real_session_maker(*s_args, **s_kwargs)
        monkeypatch.setattr(session, "flush", MagicMock(side_effect=RuntimeError("Simulated flush failure")))
        return session

    monkeypatch.setattr("scripts.provision_staging_user.SessionLocal", failing_flush_session)

    with pytest.raises(RuntimeError, match="Simulated flush failure"):
        provision_staging_user(args)

    db = real_session_maker()
    assert db.query(User).filter(User.id == "usr-flush-fail-01").first() is None
    assert db.query(Consent).count() == 0
    assert db.query(AuditLog).count() == 0
    db.close()


def test_identity_guard_accepts_matching_staging_target():
    """Positively accepts exact database name and exact host match with port normalization."""
    mock_engine = MagicMock()
    mock_engine.dialect.name = "postgresql"
    mock_engine.url.database = "lifelink_staging"
    mock_engine.url.host = "dpg-c1234567890-a.oregon-postgres.render.com"
    mock_engine.url.port = 5432

    # 1. Exact host match
    result = verify_staging_database_identity(
        target_engine=mock_engine,
        expected_db_name="lifelink_staging",
        expected_db_host="dpg-c1234567890-a.oregon-postgres.render.com",
    )
    assert result["verified"] is True
    assert result["database"] == "lifelink_staging"
    assert result["host"] == "dpg-c1234567890-a.oregon-postgres.render.com"
    assert result["port"] == 5432

    # 2. Case-insensitivity and host:port normalization in expected input
    result_norm = verify_staging_database_identity(
        target_engine=mock_engine,
        expected_db_name="LifeLink_Staging",
        expected_db_host="DPG-C1234567890-A.OREGON-POSTGRES.RENDER.COM:5432",
    )
    assert result_norm["verified"] is True


def test_identity_guard_rejects_missing_expected_identity():
    """Fails closed if either expected database name or host is missing or blank."""
    mock_engine = MagicMock()
    mock_engine.url.database = "lifelink_staging"
    mock_engine.url.host = "dpg-render.com"

    for db_val, host_val in [
        (None, "dpg-render.com"),
        ("lifelink_staging", None),
        ("", "dpg-render.com"),
        ("lifelink_staging", ""),
        ("   ", "dpg-render.com"),
        (None, None),
    ]:
        with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Expected staging database identity is not configured"):
            verify_staging_database_identity(
                target_engine=mock_engine,
                expected_db_name=db_val,
                expected_db_host=host_val,
            )


def test_identity_guard_rejects_mismatched_database_name():
    """Fails closed if the resolved database name does not match expected staging database."""
    mock_engine = MagicMock()
    mock_engine.url.database = "lifelink_development"
    mock_engine.url.host = "dpg-staging.oregon-postgres.render.com"

    with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Database name mismatch"):
        verify_staging_database_identity(
            target_engine=mock_engine,
            expected_db_name="lifelink_staging",
            expected_db_host="dpg-staging.oregon-postgres.render.com",
        )


def test_identity_guard_rejects_mismatched_host():
    """Fails closed if the resolved host does not match expected staging host."""
    mock_engine = MagicMock()
    mock_engine.url.database = "lifelink_staging"
    mock_engine.url.host = "unauthorized-cluster.render.com"

    with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Database host mismatch"):
        verify_staging_database_identity(
            target_engine=mock_engine,
            expected_db_name="lifelink_staging",
            expected_db_host="expected-cluster.render.com",
        )


def test_identity_guard_rejects_production_and_system_targets():
    """Refuses execution against production, canonical, or system databases."""
    forbidden_targets = [
        ("lifelink_prod", "staging-host.render.com"),
        ("lifelink_production", "staging-host.render.com"),
        ("lifelink_canonical", "staging-host.render.com"),
        ("postgres", "staging-host.render.com"),
        ("template0", "staging-host.render.com"),
        ("template1", "staging-host.render.com"),
        ("lifelink_staging", "production-db.internal"),
        ("lifelink_staging", "prod-cluster.render.com"),
    ]

    for db_name, host_name in forbidden_targets:
        mock_engine = MagicMock()
        mock_engine.url.database = db_name
        mock_engine.url.host = host_name

        with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Target database .* matches prohibited production.* naming|protected system"):
            verify_staging_database_identity(
                target_engine=mock_engine,
                expected_db_name=db_name,
                expected_db_host=host_name,
            )

    # Also refuse if operator configures a production name as the expected identity
    mock_engine = MagicMock()
    mock_engine.url.database = "lifelink_prod"
    mock_engine.url.host = "some-host"
    with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Target database .* matches prohibited production.* naming"):
        verify_staging_database_identity(
            target_engine=mock_engine,
            expected_db_name="lifelink_prod",
            expected_db_host="some-host",
        )


def test_identity_guard_redacts_credentials_in_error_messages():
    """Ensures error messages never expose database credentials or full connection strings."""
    secret_pwd = "SuperSecretDbPassword123!"
    secret_user = "secret_admin_user"

    mock_engine = MagicMock()
    mock_engine.url.database = "wrong_db"
    mock_engine.url.host = "target-host.render.com"
    mock_engine.url.password = secret_pwd
    mock_engine.url.username = secret_user

    with pytest.raises(RuntimeError) as exc_info:
        verify_staging_database_identity(
            target_engine=mock_engine,
            expected_db_name="lifelink_staging",
            expected_db_host="target-host.render.com",
        )

    err_str = str(exc_info.value)
    assert secret_pwd not in err_str
    assert secret_user not in err_str
    assert "wrong_db" in err_str
    assert "lifelink_staging" in err_str


def test_staging_guard_fails_closed_when_identity_unconfigured(monkeypatch):
    """Verifies that verify_staging_environment_guards fails closed when identity is omitted in staging."""
    monkeypatch.setattr("app.core.config.settings.APP_ENV", "staging")
    fake_engine = MagicMock()
    fake_engine.dialect.name = "postgresql"
    monkeypatch.setattr("scripts.provision_staging_user.engine", fake_engine)

    # Calling without expected_db_name or expected_db_host
    with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Expected staging database identity is not configured"):
        verify_staging_environment_guards()


def test_server_database_identity_verification_success():
    """Verifies verify_server_database_identity succeeds when server returns matching database name."""
    mock_db = MagicMock()
    mock_execute = MagicMock()
    mock_execute.scalar.return_value = "lifelink_staging"
    mock_db.execute.return_value = mock_execute

    result = verify_server_database_identity(mock_db, "lifelink_staging")
    assert result == "lifelink_staging"


def test_server_database_identity_verification_mismatch():
    """Verifies verify_server_database_identity fails closed when server returns different database."""
    mock_db = MagicMock()
    mock_execute = MagicMock()
    mock_execute.scalar.return_value = "postgres"
    mock_db.execute.return_value = mock_execute

    with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Server-side database identity mismatch"):
        verify_server_database_identity(mock_db, "lifelink_staging")


def test_server_database_identity_verification_query_error():
    """Verifies verify_server_database_identity fails closed when query execution fails."""
    mock_db = MagicMock()
    mock_db.execute.side_effect = Exception("Connection terminated")

    with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Failed to query server-side database identity"):
        verify_server_database_identity(mock_db, "lifelink_staging")


def test_server_database_identity_verification_empty_return():
    """Verifies verify_server_database_identity fails closed when query returns empty/None."""
    mock_db = MagicMock()
    mock_execute = MagicMock()
    mock_execute.scalar.return_value = None
    mock_db.execute.return_value = mock_execute

    with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Server returned an empty database name"):
        verify_server_database_identity(mock_db, "lifelink_staging")
