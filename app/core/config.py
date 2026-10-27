import os
import json
from typing import List, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "LifeLink Emergency Intelligence Network"
    VERSION: str = "2.0.0"

    @field_validator("APP_ENV", mode="before")
    @classmethod
    def normalize_app_env(cls, v: str) -> str:
        if isinstance(v, str):
            clean = v.strip().lower()
            if clean in ("prod", "production"):
                return "production"
            elif clean in ("stage", "staging"):
                return "staging"
            return clean
        return "development"

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

    # Blood Donor Matching & Progressive Search Radius Configuration
    DONOR_SEARCH_INITIAL_RADIUS_KM: float = 2.0
    DONOR_SEARCH_MAX_RADIUS_KM: float = 20.0
    DONOR_SEARCH_EXPANSION_TIERS: List[float] = [2.0, 5.0, 10.0, 20.0]
    DONOR_SEARCH_MIN_CANDIDATES: int = 3

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

    @model_validator(mode="after")
    def validate_environment_security(self) -> "Settings":
        """
        Fail-fast validation for staging and production environments:
        1. Refuses boot with known insecure development JWT fallback or placeholder secrets.
        2. Prohibits silent fallback to SQLite and mandates an explicit PostgreSQL database URL.
        3. Leaves local development and test environments fully functional with default development settings.
        """
        env = (self.APP_ENV or "development").strip().lower()
        if env in ("staging", "production"):
            # 1. JWT Secret Validation (SEC-06)
            known_insecure_secrets = {
                "dev_insecure_jwt_secret_key_change_in_production_lifelink_2026",
                "change_this_secret_in_production_lifelink_jwt_key",
                "lifelink-super-secret-key-change-in-production-2026",
                "your_secret_key",
                "changeme",
                "secret",
                "placeholder",
                "password",
                "jwt_secret",
                "admin",
                "12345678",
                "test_secret",
            }
            jwt_secret = self.JWT_SECRET_KEY.strip() if self.JWT_SECRET_KEY else ""
            if not jwt_secret:
                raise ValueError(
                    f"Invalid JWT_SECRET_KEY: APP_ENV='{self.APP_ENV}' requires an explicitly configured, secure JWT secret key. "
                    "JWT_SECRET_KEY cannot be empty or missing in staging and production."
                )

            if jwt_secret.lower() in known_insecure_secrets:
                raise ValueError(
                    f"Invalid JWT_SECRET_KEY: APP_ENV='{self.APP_ENV}' requires an explicitly configured, secure JWT secret key. "
                    "The development fallback or placeholder secret is strictly prohibited in staging and production."
                )

            insecure_indicators = ["dev", "insecure", "change_in_production", "placeholder", "example"]
            if any(indicator in jwt_secret.lower() for indicator in insecure_indicators):
                raise ValueError(
                    f"Invalid JWT_SECRET_KEY: APP_ENV='{self.APP_ENV}' requires a genuine production secret. "
                    "Development indicators or placeholder keywords are not permitted."
                )

            if len(jwt_secret) < 32:
                raise ValueError(
                    f"Invalid JWT_SECRET_KEY: APP_ENV='{self.APP_ENV}' requires a secure JWT secret key of at least 32 characters for HS256."
                )

            # 2. Database URL Validation (Must be PostgreSQL, never SQLite or unconfigured)
            db_url = self.DATABASE_URL.strip() if self.DATABASE_URL else ""
            if not db_url or db_url.startswith("sqlite"):
                raise ValueError(
                    f"Invalid DATABASE_URL: APP_ENV='{self.APP_ENV}' requires an explicitly configured PostgreSQL database URL. "
                    "Silent fallback to SQLite or an unconfigured database target is strictly prohibited."
                )

            if not (db_url.startswith("postgresql+psycopg://") or db_url.startswith("postgresql://")):
                raise ValueError(
                    f"Invalid DATABASE_URL: APP_ENV='{self.APP_ENV}' requires a PostgreSQL dialect URL "
                    "(e.g., postgresql+psycopg://<user>:<password>@<host>:<port>/<dbname>)."
                )

            # 3. Malformed PostgreSQL URL Validation
            try:
                from sqlalchemy.engine import make_url
                parsed = make_url(db_url)
            except Exception:
                raise ValueError(
                    f"Invalid DATABASE_URL: APP_ENV='{self.APP_ENV}' requires a well-formed PostgreSQL URL "
                    "(e.g., postgresql+psycopg://<user>:<password>@<host>:<port>/<dbname>)."
                )

            if not parsed.database or not parsed.database.strip():
                raise ValueError(
                    f"Invalid DATABASE_URL: APP_ENV='{self.APP_ENV}' requires a well-formed PostgreSQL URL "
                    "containing a valid target database name (e.g., postgresql+psycopg://<user>:<password>@<host>:<port>/<dbname>)."
                )

            # 4. CORS Origins Validation (SEC-07)
            cors_list = self.CORS_ORIGINS if isinstance(self.CORS_ORIGINS, list) else [self.CORS_ORIGINS]
            if not cors_list or len(cors_list) == 0:
                raise ValueError(
                    f"Invalid CORS_ORIGINS: APP_ENV='{self.APP_ENV}' requires explicit allowed origins. "
                    "CORS_ORIGINS cannot be empty in staging and production."
                )
            if "*" in cors_list:
                raise ValueError(
                    f"Invalid CORS_ORIGINS: APP_ENV='{self.APP_ENV}' prohibits wildcard ('*') origins. "
                    "Explicit frontend domains must be specified."
                )

            # 5. Production Seeding Guard (SEC-08)
            if self.AUTO_SEED_DATA:
                raise ValueError(
                    f"Invalid configuration: AUTO_SEED_DATA cannot be True in APP_ENV='{self.APP_ENV}'. "
                    "Automatic seeding of demo records is strictly prohibited in staging and production."
                )

        return self

    def validate_startup_security(self) -> None:
        """Explicit pre-flight check called during application lifespan startup."""
        self.validate_environment_security()
        if self.APP_ENV in ("staging", "production") and self.DEMO_WRITE_GUARD_ENABLED:
            self.assert_isolated_target_for_write_testing()

    # Rate Limiting Configuration (SEC-09)
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_REGISTER: str = "3/minute"
    RATE_LIMIT_REFRESH: str = "10/minute"
    RATE_LIMIT_STORAGE_URL: str = ""  # Optional Redis URL, e.g. redis://localhost:6379/0

    # Testing & Demo Safety Guards
    DEMO_WRITE_GUARD_ENABLED: bool = False
    MOCK_NOTIFICATIONS_ONLY: bool = True
    NOTIFICATION_PROVIDER: str = "mock"  # "mock" or "twilio"
    # Live SMS Demo Safety
    TWILIO_DEMO_RECIPIENT: str = ""
    # External service configurations
    GOOGLE_MAPS_API_KEY: str = ""
    GOOGLE_MAPS_TIMEOUT_SECONDS: float = 6.0
    GOOGLE_MAPS_CACHE_TTL_SECONDS: int = 300
    GOOGLE_MAPS_TRAFFIC_AWARE: bool = True
    DONOR_SELECTION_MAX_CONTACTS: int = 3
    DONOR_BATCH_SIZE: int = 5
    DONOR_TARGET_ACCEPTED: int = 3
    TEST_CONTACT_POOL: List[str] = [
        "+919876543001",
        "+919876543002",
        "+919876543003",
        "+919876543004",
        "+919876543005",
    ]
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+14155238886"
    TWILIO_LIVE_ENABLED: bool = False  # Explicit authorization gate: live dispatch is disabled by default
    NOTIFICATION_RATE_LIMIT_PER_RECIPIENT_PER_HOUR: int = 5
    NOTIFICATION_SPEND_CEILING_USD: float = 100.0
    LLM_API_KEY: str = ""
    LLM_PROVIDER: str = "mock"  # "mock", "gemini", or "openai"
    LLM_MODEL_NAME: str = "gemini-1.5-flash"
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

