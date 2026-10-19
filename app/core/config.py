import os
import json
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "LifeLink Emergency Intelligence Network"
    VERSION: str = "2.0.0"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, str) and v.startswith("["):
            try:
                return json.loads(v)
            except Exception:
                return [v]
        elif isinstance(v, (list, tuple)):
            return list(v)
        return []

    # Security & Auth
    JWT_SECRET_KEY: str = "dev_insecure_jwt_secret_key_change_in_production_lifelink_2026"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database
    DATABASE_URL: str = "sqlite:///./lifelink.db"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 300
    AUTO_SEED_DATA: bool = True
    POSTGIS_ENABLED: bool = False

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if not v:
            v = "sqlite:///./lifelink.db"
        # Standardize postgresql:// or postgres:// to postgresql+psycopg:// for psycopg 3 driver
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+psycopg://", 1)
        elif v.startswith("postgresql://") and not v.startswith("postgresql+"):
            return v.replace("postgresql://", "postgresql+psycopg://", 1)

        # Deterministic resolution: if relative default SQLite path is used, resolve to canonical backend database
        if v in ("sqlite:///./lifelink.db", "sqlite:///lifelink.db"):
            backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            canonical_db_path = os.path.join(backend_dir, "lifelink.db")
            if os.path.exists(canonical_db_path):
                norm_path = canonical_db_path.replace("\\", "/")
                return f"sqlite:///{norm_path}"
        return v

    # Testing & Demo Safety Guards
    DEMO_WRITE_GUARD_ENABLED: bool = False
    MOCK_NOTIFICATIONS_ONLY: bool = True
    NOTIFICATION_PROVIDER: str = "mock"  # "mock" or "twilio"

    # External service configurations
    GOOGLE_MAPS_API_KEY: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+14155238886"
    TWILIO_LIVE_ENABLED: bool = False  # Explicit authorization gate: live dispatch is disabled by default
    NOTIFICATION_RATE_LIMIT_PER_RECIPIENT_PER_HOUR: int = 5
    NOTIFICATION_SPEND_CEILING_USD: float = 100.0
    LLM_API_KEY: str = ""
    VECTOR_DATABASE_URL: str = ""

    def get_sanitized_database_info(self) -> dict:
        """Returns safe diagnostic information regarding the resolved database target without credentials."""
        url = self.DATABASE_URL
        dialect = "sqlite" if url.startswith("sqlite") else url.split("://")[0]
        
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        root_dir = os.path.abspath(os.path.join(backend_dir, ".."))
        canonical_path = os.path.normcase(os.path.abspath(os.path.join(backend_dir, "lifelink.db")))
        root_legacy_path = os.path.normcase(os.path.abspath(os.path.join(root_dir, "lifelink.db")))

        is_canonical = False
        is_legacy_root = False
        is_sandbox = False

        if url.startswith("sqlite"):
            if ":memory:" in url:
                target = ":memory:"
                is_sandbox = True
            else:
                path_part = url.replace("sqlite:///", "").replace("/", os.sep)
                norm_target = os.path.normcase(os.path.abspath(path_part))
                target = norm_target
                is_canonical = (norm_target == canonical_path)
                is_legacy_root = (norm_target == root_legacy_path)
                if "sandbox" in norm_target or "test" in norm_target:
                    is_sandbox = True
        else:
            try:
                from sqlalchemy.engine import make_url
                target = make_url(url).render_as_string(hide_password=True)
            except Exception:
                target = f"{dialect}://***@host/db"

        return {
            "dialect": dialect,
            "resolved_target": target,
            "is_canonical": is_canonical,
            "is_legacy_root": is_legacy_root,
            "is_sandbox": is_sandbox,
        }

    def assert_isolated_target_for_write_testing(self) -> None:
        """Guarantees that write-oriented tests or demo simulations cannot run against canonical/legacy databases."""
        info = self.get_sanitized_database_info()
        if info["is_canonical"] or info["is_legacy_root"]:
            raise RuntimeError(
                f"PROTECTED DATABASE GUARD: Target '{info['resolved_target']}' is a protected canonical or legacy database. "
                "Write-oriented tests or demonstrations must specify an isolated sandbox database (e.g. lifelink_demo_sandbox.db or :memory:)."
            )

    _backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    model_config = SettingsConfigDict(
        env_file=(".env", os.path.join(_backend_dir, ".env")),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )


settings = Settings()


def verify_isolated_postgresql_test_target(url: str) -> dict:
    """
    Strict safety guard: Positively verifies that a database URL points to an isolated,
    disposable PostgreSQL test database before any migration or write test operation.
    Refuses execution against SQLite, canonical, production, or unidentified databases.
    """
    if not url:
        raise ValueError("Database URL must not be empty.")

    from sqlalchemy.engine import make_url

    try:
        parsed = make_url(url)
    except Exception as exc:
        raise ValueError(f"Invalid database URL format: {exc}") from exc

    # 1. Dialect check
    dialect = parsed.get_backend_name()
    if dialect != "postgresql":
        raise RuntimeError(
            f"SAFETY REFUSAL: Target dialect is '{dialect}'. "
            "Only genuine PostgreSQL instances are permitted for PostgreSQL integration verification."
        )

    # 2. Database identity check
    db_name = (parsed.database or "").strip().lower()
    if not db_name:
        raise RuntimeError("SAFETY REFUSAL: PostgreSQL database name cannot be empty.")

    # Disallowed production or system databases
    forbidden_names = {
        "lifelink",
        "lifelink_prod",
        "lifelink_production",
        "postgres",
        "template0",
        "template1",
        "defaultdb",
    }
    if db_name in forbidden_names:
        raise RuntimeError(
            f"SAFETY REFUSAL: Database '{db_name}' is a protected production, canonical, or system database name. "
            "Integration tests require an isolated test database (e.g. 'lifelink_test' or 'lifelink_disposable_test')."
        )

    # Positively require test or disposable identifier in database name
    required_keywords = ("test", "disposable", "sandbox", "ci")
    if not any(kw in db_name for kw in required_keywords):
        raise RuntimeError(
            f"SAFETY REFUSAL: Database name '{db_name}' does not contain a recognized test identifier "
            f"({', '.join(required_keywords)}). Aborting to prevent accidental write to unverified database."
        )

    sanitized_url = parsed.render_as_string(hide_password=True)
    return {
        "dialect": dialect,
        "database": parsed.database,
        "host": parsed.host or "localhost",
        "port": parsed.port or 5432,
        "username": parsed.username or "postgres",
        "sanitized_target": sanitized_url,
        "is_verified_test_target": True,
    }

