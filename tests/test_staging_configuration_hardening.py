"""
Focused regression tests for Staging Configuration Hardening and Seeding Protection.
Verifies fail-fast validation in Settings and hard demo-seeding guards in init_db.
Uses isolated in-memory test databases and mocks; does not mutate project databases.
"""
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, settings
from app.db.base import Base
from app.db.init_db import init_db
from app.models.user import User
from app.models.hospital import Hospital


# -----------------------------------------------------------------------------
# Task 1: Configuration Validation Tests
# -----------------------------------------------------------------------------

def test_staging_insecure_jwt_fallback_rejected():
    """Staging cannot start with the known insecure development JWT fallback."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="staging",
            DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/lifelink_staging",
            # JWT_SECRET_KEY omitted -> defaults to insecure fallback
        )
    err = str(exc_info.value)
    assert "Invalid JWT_SECRET_KEY" in err
    assert "development fallback or placeholder" in err
    # Must not leak secret value
    assert "dev_insecure_jwt_secret_key" not in err


@pytest.mark.parametrize(
    "placeholder",
    [
        "dev_insecure_jwt_secret_key_change_in_production_lifelink_2026",
        "change_this_secret_in_production_lifelink_jwt_key",
        "your_secret_key",
        "changeme",
        "secret",
        "placeholder",
        "",
        "   ",
    ],
)
def test_staging_placeholder_jwt_secrets_rejected(placeholder):
    """Staging refuses empty, whitespace, and known placeholder JWT secrets."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="staging",
            JWT_SECRET_KEY=placeholder,
            DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/lifelink_staging",
        )
    assert "Invalid JWT_SECRET_KEY" in str(exc_info.value)


def test_production_insecure_jwt_secret_rejected():
    """Production cannot start with default insecure JWT fallback."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="production",
            DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/lifelink_prod",
        )
    assert "Invalid JWT_SECRET_KEY" in str(exc_info.value)


def test_staging_short_jwt_secret_rejected():
    """Staging rejects custom JWT secrets shorter than 32 characters."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="staging",
            JWT_SECRET_KEY="short_secret_under_32_chars",  # 27 chars
            DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/lifelink_staging",
        )
    err = str(exc_info.value)
    assert "Invalid JWT_SECRET_KEY" in err
    assert "at least 32 characters" in err
    # Must not leak the secret value
    assert "short_secret_under_32_chars" not in err


def test_staging_valid_32_character_jwt_secret_accepted():
    """Staging accepts a secret with exactly 32 or more characters."""
    s = Settings(
        APP_ENV="staging",
        JWT_SECRET_KEY="12345678901234567890123456789012",  # exactly 32 chars
        DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/lifelink_staging",
    )
    assert s.APP_ENV == "staging"
    assert len(s.JWT_SECRET_KEY) == 32


def test_staging_sqlite_fallback_rejected():
    """Staging cannot silently fall back to default SQLite database."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="staging",
            JWT_SECRET_KEY="staging_cryptographic_secret_value_12345",
            # DATABASE_URL omitted -> defaults to sqlite:///./lifelink.db
        )
    err = str(exc_info.value)
    assert "Invalid DATABASE_URL" in err
    assert "sqlite" in err.lower()


@pytest.mark.parametrize(
    "sqlite_url",
    [
        "sqlite:///./lifelink.db",
        "sqlite:////absolute/path/to/db.sqlite",
        "sqlite:///:memory:",
        "",
        "   ",
    ],
)
def test_staging_explicit_sqlite_or_empty_rejected(sqlite_url):
    """Staging refuses explicit SQLite targets and empty database URLs."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="staging",
            JWT_SECRET_KEY="staging_cryptographic_secret_value_12345",
            DATABASE_URL=sqlite_url,
        )
    assert "Invalid DATABASE_URL" in str(exc_info.value)


def test_staging_non_postgres_dialect_rejected():
    """Staging rejects non-PostgreSQL database dialects."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="staging",
            JWT_SECRET_KEY="staging_cryptographic_secret_value_12345",
            DATABASE_URL="mysql://user:pass@localhost:3306/lifelink_staging",
        )
    err = str(exc_info.value)
    assert "Invalid DATABASE_URL" in err
    assert "PostgreSQL dialect" in err


@pytest.mark.parametrize(
    "malformed_url",
    [
        "postgresql+psycopg://",
        "postgresql+psycopg:///",
        "postgresql+psycopg://localhost",
        "postgresql+psycopg://localhost:5432",
        "postgresql+psycopg://localhost:5432/",
        "postgresql+psycopg://user:pass@localhost:5432",
        "postgresql+psycopg://user:pass@localhost:5432/",
    ],
)
def test_staging_malformed_postgres_url_rejected(malformed_url):
    """Staging safely rejects malformed PostgreSQL URLs missing a database name."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="staging",
            JWT_SECRET_KEY="staging_cryptographic_secret_value_12345",
            DATABASE_URL=malformed_url,
        )
    err = str(exc_info.value)
    assert "Invalid DATABASE_URL" in err
    assert "well-formed PostgreSQL URL" in err


@pytest.mark.parametrize("whitespace_env", [" staging ", " STAGING\t", " production ", " PRODUCTION\n"])
def test_settings_normalizes_whitespace_in_app_env(whitespace_env):
    """Surrounding whitespace or mixed casing in APP_ENV triggers staging/production validation."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV=whitespace_env,
            # Missing secret and DB URL -> must trigger validation!
        )
    assert "Invalid JWT_SECRET_KEY" in str(exc_info.value)


def test_staging_valid_explicit_configuration_accepted():
    """Staging boots cleanly when provided an explicit secret and PostgreSQL URL."""
    s = Settings(
        APP_ENV="staging",
        JWT_SECRET_KEY="staging_cryptographic_secret_value_12345",
        DATABASE_URL="postgresql+psycopg://staging_user:staging_pass@db.staging.internal:5432/lifelink_staging",
    )
    assert s.APP_ENV == "staging"
    assert s.DATABASE_URL == "postgresql+psycopg://staging_user:staging_pass@db.staging.internal:5432/lifelink_staging"


def test_staging_normalizes_standard_postgres_url():
    """postgresql:// scheme is safely standardized to postgresql+psycopg:// in staging."""
    s = Settings(
        APP_ENV="staging",
        JWT_SECRET_KEY="staging_cryptographic_secret_value_12345",
        DATABASE_URL="postgresql://staging_user:staging_pass@localhost:5432/lifelink_staging",
    )
    assert s.DATABASE_URL.startswith("postgresql+psycopg://")


def test_production_valid_explicit_configuration_accepted():
    """Production boots cleanly when provided an explicit secret and PostgreSQL URL."""
    s = Settings(
        APP_ENV="production",
        JWT_SECRET_KEY="prod_cryptographic_secret_value_67890",
        DATABASE_URL="postgresql+psycopg://prod_user:prod_pass@db.prod.internal:5432/lifelink_production",
    )
    assert s.APP_ENV == "production"
    assert "lifelink_production" in s.DATABASE_URL


def test_development_defaults_remain_compatible():
    """Local development environment preserves frictionless defaults without validation error."""
    # 1. Isolated class defaults (without loading local .env)
    s_default = Settings(_env_file=None, APP_ENV="development")
    assert s_default.APP_ENV == "development"
    assert s_default.JWT_SECRET_KEY == "dev_insecure_jwt_secret_key_change_in_production_lifelink_2026"
    assert s_default.DATABASE_URL.startswith("sqlite")

    # 2. Development environment with local config loads cleanly without validation error
    s_local = Settings(APP_ENV="development")
    assert s_local.APP_ENV == "development"
    assert s_local.DATABASE_URL.startswith("sqlite")


# -----------------------------------------------------------------------------
# Task 2: Demo Seeding Protection Tests
# -----------------------------------------------------------------------------

@pytest.fixture
def isolated_empty_db():
    """Creates an isolated in-memory database with tables created, containing 0 rows."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_seeding_blocked_in_staging_even_if_auto_seed_true(monkeypatch, isolated_empty_db):
    """Demo seeding is strictly blocked in staging even when AUTO_SEED_DATA=True."""
    monkeypatch.setattr(settings, "APP_ENV", "staging")
    monkeypatch.setattr(settings, "AUTO_SEED_DATA", True)

    init_db(isolated_empty_db)

    # Must remain completely empty
    assert isolated_empty_db.query(User).count() == 0
    assert isolated_empty_db.query(Hospital).count() == 0


def test_seeding_blocked_in_production_even_if_auto_seed_true(monkeypatch, isolated_empty_db):
    """Demo seeding is strictly blocked in production even when AUTO_SEED_DATA=True."""
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "AUTO_SEED_DATA", True)

    init_db(isolated_empty_db)

    # Must remain completely empty
    assert isolated_empty_db.query(User).count() == 0
    assert isolated_empty_db.query(Hospital).count() == 0


def test_seeding_skipped_in_development_when_auto_seed_false(monkeypatch, isolated_empty_db):
    """In development, setting AUTO_SEED_DATA=False correctly skips demo seeding."""
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "AUTO_SEED_DATA", False)

    init_db(isolated_empty_db)

    assert isolated_empty_db.query(User).count() == 0
    assert isolated_empty_db.query(Hospital).count() == 0


def test_seeding_runs_in_development_when_auto_seed_true(monkeypatch, isolated_empty_db):
    """In development, setting AUTO_SEED_DATA=True correctly seeds demo records."""
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "AUTO_SEED_DATA", True)

    init_db(isolated_empty_db)

    # Demo hospitals and users must be populated
    assert isolated_empty_db.query(Hospital).count() > 0
    assert isolated_empty_db.query(User).count() > 0
    # Confirm known demo doctor user exists
    doctor = isolated_empty_db.query(User).filter_by(id="usr-doc-001").first()
    assert doctor is not None
    assert doctor.role == "doctor"


@pytest.mark.parametrize("whitespace_env", [" staging ", " PRODUCTION ", "\tstaging\n"])
def test_seeding_and_create_all_blocked_with_whitespace_app_env(monkeypatch, isolated_empty_db, whitespace_env):
    """APP_ENV with surrounding whitespace or mixed case still strictly blocks demo seeding and table creation."""
    monkeypatch.setattr(settings, "APP_ENV", whitespace_env)
    monkeypatch.setattr(settings, "AUTO_SEED_DATA", True)

    init_db(isolated_empty_db)

    # Must remain completely empty
    assert isolated_empty_db.query(User).count() == 0
    assert isolated_empty_db.query(Hospital).count() == 0
