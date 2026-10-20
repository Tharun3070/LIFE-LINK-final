import sys
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.hospital import Hospital
from app.models.donor import Donor
from app.models.user import User
from app.models.consent import Consent
from app.models.emergency import Emergency
from app.models.audit import AuditLog
from scripts.seed_staging_demo_data import (
    verify_staging_environment_guards,
    verify_staging_database_identity,
    verify_server_database_identity,
    seed_staging_demo_data,
    build_demo_hospital,
    build_demo_donors,
    parse_arguments,
    sanitize_error_message,
    DEMO_HOSPITAL_ID,
    DEMO_DONOR_IDS,
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

    # Crucial: Register pragma listener before create_all so foreign keys are enforced from inception
    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(test_engine)
    TestingSession = sessionmaker(bind=test_engine)

    # Patch SessionLocal and engine in the seeder script
    monkeypatch.setattr("scripts.seed_staging_demo_data.SessionLocal", TestingSession)
    monkeypatch.setattr("scripts.seed_staging_demo_data.engine", test_engine)

    # Monkeypatch the environment guards and server identity verification for test db isolation
    monkeypatch.setattr(
        "scripts.seed_staging_demo_data.verify_staging_environment_guards",
        lambda expected_db_name=None, expected_db_host=None: {
            "verified": True,
            "database": "test_db",
            "host": "localhost",
            "port": 5432,
        },
    )
    monkeypatch.setattr(
        "scripts.seed_staging_demo_data.verify_server_database_identity",
        lambda db, expected_db_name: expected_db_name or "test_db",
    )

    yield TestingSession
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


def test_sqlite_foreign_keys_are_enforced(mock_isolated_db):
    """Verifies SQLite foreign key pragma is active and blocks dangling user_id references."""
    db = mock_isolated_db()
    # Inserting a donor with an unresolvable user_id must fail under foreign keys
    invalid_donor = Donor(
        id="D-FK-TEST",
        user_id="usr-does-not-exist",
        blood_group="O-",
        lat=12.9,
        lng=77.5,
    )
    db.add(invalid_donor)
    with pytest.raises(Exception):  # IntegrityError / OperationalError on FK violation
        db.commit()
    db.rollback()

    # Inserting a donor with user_id=None must succeed under foreign keys
    valid_donor = Donor(
        id="D-FK-VALID",
        user_id=None,
        blood_group="O-",
        lat=12.9,
        lng=77.5,
    )
    db.add(valid_donor)
    db.commit()
    assert db.query(Donor).filter(Donor.id == "D-FK-VALID").first() is not None
    db.close()


def test_guard_fails_when_app_env_not_staging(monkeypatch):
    """Ensures seeder strictly fails closed when APP_ENV is development or production."""
    for invalid_env in ["development", "production", "test", "local", ""]:
        monkeypatch.setattr("app.core.config.settings.APP_ENV", invalid_env)
        with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Staging demo seeding is restricted to APP_ENV='staging'"):
            verify_staging_environment_guards()


def test_guard_fails_when_dialect_not_postgresql(monkeypatch):
    """Ensures seeder strictly refuses SQLite, MySQL, and any non-Postgres targets."""
    monkeypatch.setattr("app.core.config.settings.APP_ENV", "staging")
    fake_engine = MagicMock()
    fake_engine.dialect.name = "sqlite"
    monkeypatch.setattr("scripts.seed_staging_demo_data.engine", fake_engine)

    with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Staging demo seeding requires a genuine PostgreSQL database"):
        verify_staging_environment_guards()


def test_cli_rejects_broad_clean_flag(monkeypatch):
    """Verifies that the CLI cannot accept --clean and fails as unrecognized."""
    monkeypatch.setattr(sys, "argv", ["seed_staging_demo_data.py", "--clean"])
    with pytest.raises(SystemExit):
        parse_arguments()


def test_identity_guard_accepts_matching_staging_target():
    """Positively accepts exact database name and exact host match with port normalization."""
    mock_engine = MagicMock()
    mock_engine.dialect.name = "postgresql"
    mock_engine.url.drivername = "postgresql+psycopg"
    mock_engine.url.database = "lifelink_staging"
    mock_engine.url.host = "dpg-c1234567890-a.oregon-postgres.render.com"
    mock_engine.url.port = 5432

    result = verify_staging_database_identity(
        target_engine=mock_engine,
        expected_db_name="lifelink_staging",
        expected_db_host="dpg-c1234567890-a.oregon-postgres.render.com",
    )
    assert result["verified"] is True
    assert result["database"] == "lifelink_staging"
    assert result["host"] == "dpg-c1234567890-a.oregon-postgres.render.com"
    assert result["port"] == 5432

    # Case-insensitivity and host:port normalization
    result_norm = verify_staging_database_identity(
        target_engine=mock_engine,
        expected_db_name="LifeLink_Staging",
        expected_db_host="DPG-C1234567890-A.OREGON-POSTGRES.RENDER.COM:5432",
    )
    assert result_norm["verified"] is True


def test_identity_guard_rejects_missing_expected_identity():
    """Fails closed if either expected database name or host is missing or blank."""
    mock_engine = MagicMock()
    mock_engine.url.drivername = "postgresql"
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
    mock_engine.url.drivername = "postgresql"
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
    mock_engine.url.drivername = "postgresql"
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
        mock_engine.url.drivername = "postgresql"
        mock_engine.url.database = db_name
        mock_engine.url.host = host_name

        with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Target database .* matches prohibited production.* naming|protected system"):
            verify_staging_database_identity(
                target_engine=mock_engine,
                expected_db_name=db_name,
                expected_db_host=host_name,
            )


def test_identity_guard_redacts_credentials_in_error_messages():
    """Ensures error messages never expose database credentials or full connection strings."""
    secret_pwd = "SuperSecretDbPassword123!"
    secret_user = "secret_admin_user"

    mock_engine = MagicMock()
    mock_engine.url.drivername = "postgresql"
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


def test_identity_guard_rejects_ambiguous_url_formatting():
    """Fails closed if database name or host contains ambiguous characters or non-postgres driver."""
    # 1. Non-Postgres driver
    bad_engine = MagicMock()
    bad_engine.url.drivername = "mysql+pymysql"
    bad_engine.url.database = "lifelink_staging"
    bad_engine.url.host = "render.com"
    with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Target database driver .* is not a genuine PostgreSQL dialect"):
        verify_staging_database_identity(bad_engine, "lifelink_staging", "render.com")

    # 2. Ambiguous characters in database name (query string or path injection)
    mock_engine = MagicMock()
    mock_engine.url.drivername = "postgresql"
    mock_engine.url.host = "dpg-staging.render.com"
    for ambiguous_db in [
        "lifelink_staging?sslmode=require",
        "lifelink_staging#fragment",
        "lifelink_staging&param=val",
        "lifelink staging",
    ]:
        mock_engine.url.database = ambiguous_db
        with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Target database name contains ambiguous URL formatting"):
            verify_staging_database_identity(mock_engine, "lifelink_staging", "dpg-staging.render.com")

    # 3. Ambiguous characters in host (slashes, userinfo, queries)
    mock_engine.url.database = "lifelink_staging"
    for ambiguous_host in [
        "dpg-staging.render.com/path",
        "user@dpg-staging.render.com",
        "dpg-staging.render.com?query=1",
        "dpg staging.com",
    ]:
        mock_engine.url.host = ambiguous_host
        with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Target database host contains ambiguous URL formatting"):
            verify_staging_database_identity(mock_engine, "lifelink_staging", "dpg-staging.render.com")


def test_exception_sanitizer_redacts_credentials_and_secrets():
    """Directly verifies sanitize_error_message redacts URLs, passwords, and tokens."""
    raw_message = (
        "OperationalError: connection to server at 'postgresql+psycopg://admin_user:P@ssw0rd!123@dpg-c123.render.com:5432/lifelink_staging' "
        "failed: password=P@ssw0rd!123 auth_token='my-secret-token'"
    )
    sanitized = sanitize_error_message(raw_message)

    assert "P@ssw0rd!123" not in sanitized
    assert "admin_user" not in sanitized
    assert "my-secret-token" not in sanitized
    assert "[REDACTED" in sanitized


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


def test_server_database_identity_verification_query_error_sanitized():
    """Verifies verify_server_database_identity sanitizes exceptions if query execution fails."""
    mock_db = MagicMock()
    mock_db.execute.side_effect = Exception("Connection closed abruptly with secret: P@ssword999!")

    with pytest.raises(RuntimeError) as exc_info:
        verify_server_database_identity(mock_db, "lifelink_staging")

    err_str = str(exc_info.value)
    assert "P@ssword999!" not in err_str
    assert "Failed to query server-side database identity" in err_str


def test_server_database_identity_verification_empty_return():
    """Verifies verify_server_database_identity fails closed when query returns empty/None."""
    mock_db = MagicMock()
    mock_execute = MagicMock()
    mock_execute.scalar.return_value = None
    mock_db.execute.return_value = mock_execute

    with pytest.raises(RuntimeError, match="SAFETY REFUSAL: Server returned an empty database name"):
        verify_server_database_identity(mock_db, "lifelink_staging")


def test_dry_run_creates_no_records(mock_isolated_db):
    """Verifies dry-run mode (confirm=False) performs preflight checks and writes 0 records."""
    args = MagicMock()
    args.confirm = False
    args.expected_db_name = "lifelink_staging"
    args.expected_db_host = "dpg-staging.render.com"

    result = seed_staging_demo_data(args)

    assert result["status"] == "dry_run"
    assert result["created"] is False
    assert result["hospital_id"] == DEMO_HOSPITAL_ID
    assert result["donor_ids"] == DEMO_DONOR_IDS

    # Check isolated database has 0 records
    db = mock_isolated_db()
    assert db.query(Hospital).count() == 0
    assert db.query(Donor).count() == 0
    assert db.query(User).count() == 0
    assert db.query(Consent).count() == 0
    assert db.query(Emergency).count() == 0
    assert db.query(AuditLog).count() == 0
    db.close()


def test_confirmed_execution_creates_exact_four_records_with_correct_metadata(mock_isolated_db):
    """Verifies that running with --confirm creates exactly 1 hospital and 3 synthetic donors in one transaction."""
    args = MagicMock()
    args.confirm = True
    args.expected_db_name = "lifelink_staging"
    args.expected_db_host = "dpg-staging.render.com"

    result = seed_staging_demo_data(args)

    assert result["status"] == "created"
    assert result["created"] is True
    assert result["hospital_id"] == DEMO_HOSPITAL_ID
    assert result["donor_ids"] == DEMO_DONOR_IDS

    db = mock_isolated_db()

    # 1. Exactly 1 Hospital created with explicit synthetic demo labeling
    hospitals = db.query(Hospital).all()
    assert len(hospitals) == 1
    h = hospitals[0]
    assert h.id == "city-hospital-001"
    assert h.name == "City General Hospital"
    assert h.address == "100 Emergency Care Boulevard (Synthetic Demo Facility)"
    assert h.city == "Bengaluru"
    assert h.lat == 12.9716
    assert h.lng == 77.5946
    assert h.type == "Level 1 Trauma Center (Synthetic Demo)"
    assert h.blood_bank_available is True
    assert h.organ_transplant_center is True
    assert h.emergency_bays == 12
    assert h.is_current_hospital is True

    # 2. Exactly 3 Donors created with explicit synthetic demo labeling
    donors = db.query(Donor).order_by(Donor.id).all()
    assert len(donors) == 3

    donor_map = {d.id: d for d in donors}
    assert set(donor_map.keys()) == {"D-DEMO-001", "D-DEMO-002", "D-DEMO-003"}

    # Blood group assignments
    assert donor_map["D-DEMO-001"].blood_group == "O-"
    assert donor_map["D-DEMO-002"].blood_group == "A+"
    assert donor_map["D-DEMO-003"].blood_group == "O+"

    # Verify synthetic metadata and null user IDs for EVERY donor
    for d_id, donor in donor_map.items():
        assert donor.user_id is None, f"{d_id} user_id must be None"
        assert donor.is_synthetic is True, f"{d_id} is_synthetic must be True"
        assert donor.data_provenance == "synthetic_registry", f"{d_id} data_provenance must be synthetic_registry"
        assert donor.simulated_coordinates is True, f"{d_id} simulated_coordinates must be True"
        assert donor.location_consent_granted is False, f"{d_id} location_consent_granted must be False"
        assert donor.status == "available", f"{d_id} status must be available"
        assert donor.eligibility_reason == "Synthetic benchmark profile (Fictional Demo)"
        assert donor.contacted_at is None
        assert donor.responded_at is None
        # Fictional Bengaluru coordinates near the hospital (lat ~12.96-12.98, lng ~77.58-77.61)
        assert 12.95 <= donor.lat <= 13.00, f"{d_id} latitude out of Bengaluru demo range"
        assert 77.55 <= donor.lng <= 77.65, f"{d_id} longitude out of Bengaluru demo range"

    # 3. Assert zero side-effect records created
    assert db.query(User).count() == 0
    assert db.query(Consent).count() == 0
    assert db.query(Emergency).count() == 0
    assert db.query(AuditLog).count() == 0

    db.close()


def test_hospital_id_collision_causes_safe_refusal_no_modifications(mock_isolated_db):
    """Verifies that an existing hospital ID collision causes safe refusal with zero records written or changed."""
    db = mock_isolated_db()
    existing_hospital = Hospital(
        id=DEMO_HOSPITAL_ID,
        name="Pre-existing Hospital That Must Not Change",
        address="123 Historic Road",
        city="Bengaluru",
        lat=12.9100,
        lng=77.5200,
        type="clinic",
        blood_bank_available=False,
    )
    db.add(existing_hospital)
    db.commit()

    args = MagicMock()
    args.confirm = True
    args.expected_db_name = "lifelink_staging"
    args.expected_db_host = "dpg-staging.render.com"

    with pytest.raises(RuntimeError, match="COLLISION REFUSAL: Target database already contains matching demo record"):
        seed_staging_demo_data(args)

    # Verify hospital record was not modified and zero donors were created
    h = db.query(Hospital).filter(Hospital.id == DEMO_HOSPITAL_ID).first()
    assert h is not None
    assert h.name == "Pre-existing Hospital That Must Not Change"
    assert h.blood_bank_available is False
    assert db.query(Donor).count() == 0
    db.close()


def test_donor_id_collision_causes_safe_refusal_no_modifications(mock_isolated_db):
    """Verifies that an existing donor ID collision causes safe refusal with zero records written or changed."""
    db = mock_isolated_db()
    existing_donor = Donor(
        id="D-DEMO-002",
        user_id=None,
        blood_group="B+",
        lat=12.9200,
        lng=77.5300,
        status="unavailable",
    )
    db.add(existing_donor)
    db.commit()

    args = MagicMock()
    args.confirm = True
    args.expected_db_name = "lifelink_staging"
    args.expected_db_host = "dpg-staging.render.com"

    with pytest.raises(RuntimeError, match="COLLISION REFUSAL: Target database already contains matching demo record"):
        seed_staging_demo_data(args)

    # Verify existing donor is completely untouched and 0 hospitals or other donors were created
    d = db.query(Donor).filter(Donor.id == "D-DEMO-002").first()
    assert d is not None
    assert d.blood_group == "B+"
    assert d.status == "unavailable"
    assert db.query(Hospital).count() == 0
    assert db.query(Donor).count() == 1  # Only the pre-existing one
    db.close()


def test_dry_run_checks_collisions_before_reporting(mock_isolated_db):
    """Verifies that dry-run mode identifies collisions and refuses before reporting dry-run success."""
    db = mock_isolated_db()
    existing_hosp = Hospital(
        id=DEMO_HOSPITAL_ID,
        name="Existing Hospital",
        address="Address",
        city="Bengaluru",
        lat=12.97,
        lng=77.59,
    )
    db.add(existing_hosp)
    db.commit()

    args = MagicMock()
    args.confirm = False
    args.expected_db_name = "lifelink_staging"
    args.expected_db_host = "dpg-staging.render.com"

    with pytest.raises(RuntimeError, match="COLLISION REFUSAL: Target database already contains matching demo record"):
        seed_staging_demo_data(args)

    assert db.query(Donor).count() == 0
    db.close()


def test_failure_midway_rolls_back_all_four_inserts_with_sanitized_error(mock_isolated_db, monkeypatch):
    """Verifies that if commit fails midway, all inserts are rolled back and the error is sanitized."""
    args = MagicMock()
    args.confirm = True
    args.expected_db_name = "lifelink_staging"
    args.expected_db_host = "dpg-staging.render.com"

    real_session_maker = mock_isolated_db

    def failing_session(*s_args, **s_kwargs):
        session = real_session_maker(*s_args, **s_kwargs)
        # Include sensitive DB connection string in exception to test sanitization
        monkeypatch.setattr(
            session,
            "commit",
            MagicMock(side_effect=RuntimeError("Commit failed with url: postgresql://admin:P@ssword123@host:5432/db")),
        )
        return session

    monkeypatch.setattr("scripts.seed_staging_demo_data.SessionLocal", failing_session)

    with pytest.raises(RuntimeError) as exc_info:
        seed_staging_demo_data(args)

    err_str = str(exc_info.value)
    # Must be sanitized
    assert "P@ssword123" not in err_str
    assert "admin" not in err_str
    assert "Seeding error occurred" in err_str

    # Database must have 0 hospital and 0 donor records
    db = real_session_maker()
    assert db.query(Hospital).count() == 0
    assert db.query(Donor).count() == 0
    db.close()


def test_script_has_zero_communication_or_dispatch_side_effects(mock_isolated_db, monkeypatch):
    """
    Verifies that seeding triggers no external communications or dispatch,
    and proves seeded synthetic profiles are blocked from real emergency notifications.
    """
    from app.services.donor_service import donor_service
    from app.schemas.user import UserProfileSchema
    from fastapi import HTTPException

    # Seed the demo records
    args = MagicMock()
    args.confirm = True
    args.expected_db_name = "lifelink_staging"
    args.expected_db_host = "dpg-staging.render.com"

    result = seed_staging_demo_data(args)
    assert result["status"] == "created"

    db = mock_isolated_db()

    # Simulate doctor trying to contact each seeded demo donor
    mock_doctor = UserProfileSchema(
        id="usr-test-doc",
        name="Dr. Test",
        email="test.doc@lifelink.internal",
        role="doctor",
        is_verified=True,
    )

    for donor_id in DEMO_DONOR_IDS:
        # donor_service.contact_donor MUST raise HTTP 403 Forbidden because is_synthetic=True
        with pytest.raises(HTTPException) as exc_info:
            donor_service.contact_donor(
                db=db,
                donor_id=donor_id,
                emergency_id="emg-test-01",
                current_user=mock_doctor,
            )
        assert exc_info.value.status_code == 403
        assert "synthetic benchmark profile" in str(exc_info.value.detail).lower()

    db.close()


def test_donor_ranking_logic_stored_vs_recalculated(mock_isolated_db):
    """
    Verifies donor ranking behavior:
    - Static listing (get_all) uses stored baseline values.
    - Emergency ranking (get_ranked_donors) dynamically recalculates ranks and scores
      based on proximity and compatibility without altering clinical compatibility rules.
    """
    from app.services.donor_service import donor_service
    from app.models.emergency import Emergency
    from datetime import datetime, timezone

    # 1. Seed demo records
    args = MagicMock()
    args.confirm = True
    args.expected_db_name = "lifelink_staging"
    args.expected_db_host = "dpg-staging.render.com"
    seed_staging_demo_data(args)

    db = mock_isolated_db()

    # 2. Verify static listing returns stored values
    all_donors = donor_service.get_all(db)
    assert len(all_donors) == 3
    # In static listing, ai_rank is used as stored (1, 2, 3)
    assert [d.aiRank for d in all_donors] == [1, 2, 3]

    # 3. Create an emergency for recipient O- at City General Hospital
    now_str = datetime.now(timezone.utc).isoformat()
    emergency_o_neg = Emergency(
        id="emg-demo-o-neg",
        patient_id=None,
        type="blood",
        priority="critical",
        status="active",
        hospital_id=DEMO_HOSPITAL_ID,
        hospital_name="City General Hospital",
        description="Demo blood emergency O-",
        blood_group="O-",
        units_required=2,
        created_at=now_str,
        updated_at=now_str,
    )
    db.add(emergency_o_neg)
    db.commit()

    # 4. For recipient O-, clinical rules strictly require O- donor (D-DEMO-001)
    ranked_o_neg = donor_service.get_ranked_donors(db, emergency_id="emg-demo-o-neg")
    assert len(ranked_o_neg.donors) == 1
    assert ranked_o_neg.donors[0].id == "D-DEMO-001"
    assert ranked_o_neg.donors[0].bloodGroup == "O-"
    assert ranked_o_neg.donors[0].aiRank == 1
    # Check that score was dynamically computed by matching engine
    assert ranked_o_neg.donors[0].responseProbability > 0

    # 5. Create an emergency for recipient A+ (compatible with O-, A+, O+)
    emergency_a_pos = Emergency(
        id="emg-demo-a-pos",
        patient_id=None,
        type="blood",
        priority="critical",
        status="active",
        hospital_id=DEMO_HOSPITAL_ID,
        hospital_name="City General Hospital",
        description="Demo blood emergency A+",
        blood_group="A+",
        units_required=2,
        created_at=now_str,
        updated_at=now_str,
    )
    db.add(emergency_a_pos)
    db.commit()

    ranked_a_pos = donor_service.get_ranked_donors(db, emergency_id="emg-demo-a-pos")
    # All 3 donors are clinically compatible with A+
    assert len(ranked_a_pos.donors) == 3
    # Check ranks are assigned 1, 2, 3 dynamically based on total score
    assert [d.aiRank for d in ranked_a_pos.donors] == [1, 2, 3]

    db.close()
