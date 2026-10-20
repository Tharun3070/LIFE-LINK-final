#!/usr/bin/env python3
"""
LifeLink Emergency Intelligence — Guarded Staging Demo Seeder
File: scripts/seed_staging_demo_data.py

Seeds exactly ONE baseline hospital ('city-hospital-001') and THREE synthetic donor profiles
('D-DEMO-001', 'D-DEMO-002', 'D-DEMO-003') for minimal end-to-end clinical demo workflows.

Strict Safety Guards:
1. Requires APP_ENV == 'staging'.
2. Refuses to write unless --confirm flag is provided.
3. Positively verifies PostgreSQL dialect.
4. Positively verifies expected target database name and host.
5. Queries server current_database() before any write.
6. Never prints secrets, passwords, or connection URLs.
7. Checks for ID collisions before inserting; fails safely if any ID already exists.
8. Commits exactly 1 hospital and 3 donors in a single transaction; rolls back on any error.
9. Never creates users, consents, emergencies, or audit events.
10. Has zero communication or external dispatch side effects.
"""

import os
import sys
import argparse
from typing import Optional, Dict, Any, List

# Ensure backend root is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.config import settings
from app.core.logging import logger
from app.db.session import SessionLocal, engine
from app.models.hospital import Hospital
from app.models.donor import Donor

import re

# Target constant IDs
DEMO_HOSPITAL_ID = "city-hospital-001"
DEMO_DONOR_IDS = ["D-DEMO-001", "D-DEMO-002", "D-DEMO-003"]


def sanitize_error_message(error: Any) -> str:
    """
    Sanitizes exception messages to guarantee database URLs, passwords, usernames,
    tokens, query parameters, and connection secrets cannot appear in logs, traces, or terminal output.
    """
    if error is None:
        return ""
    text = str(error)

    # 1. Redact URL userinfo (e.g., postgresql://user:password@host:port/db)
    text = re.sub(r"://([^:@\s]+):([^@\s]+)@", r"://[REDACTED_USER]:[REDACTED_SECRET]@", text)
    text = re.sub(r"://([^@\s]+)@", r"://[REDACTED_USERINFO]@", text)

    # 2. Redact password/secret key-value pairs (e.g. password=..., pwd=..., secret=...)
    text = re.sub(
        r"(?i)(password|pwd|secret|token|api_?key|auth)\s*[:=]\s*['\"]?[^\s'\",;&]+",
        r"\1=[REDACTED]",
        text,
    )

    # 3. Scrub configured environment secrets if present in settings
    for secret_candidate in [
        getattr(settings, "DATABASE_URL", None),
        getattr(settings, "JWT_SECRET_KEY", None),
        getattr(settings, "TWILIO_AUTH_TOKEN", None),
        getattr(settings, "LLM_API_KEY", None),
    ]:
        if secret_candidate and isinstance(secret_candidate, str) and len(secret_candidate.strip()) >= 6:
            text = text.replace(secret_candidate.strip(), "[REDACTED_CONFIG_SECRET]")

    # 4. Remove raw psycopg / libpq DSN parameters
    text = re.sub(r"(dbname|host|user|password|port)=['\"]?[^\s'\"]+['\"]?", r"\1=[REDACTED]", text)

    return text


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Safely seed minimal demo hospital and synthetic donor records for staging.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Explicit authorization flag. Changes will ONLY be committed if this flag is present.",
    )
    parser.add_argument(
        "--expected-db-name",
        type=str,
        default=os.environ.get("EXPECTED_STAGING_DB_NAME", "").strip() or None,
        help="Expected staging PostgreSQL database name. Required for positive target identity verification.",
    )
    parser.add_argument(
        "--expected-db-host",
        type=str,
        default=os.environ.get("EXPECTED_STAGING_DB_HOST", "").strip() or None,
        help="Expected staging PostgreSQL database host. Required for positive target identity verification.",
    )
    return parser.parse_args()


def verify_staging_database_identity(
    target_engine,
    expected_db_name: Optional[str],
    expected_db_host: Optional[str],
) -> dict:
    """Positively verifies target PostgreSQL engine identity matches expected staging parameters."""
    exp_db = (expected_db_name or "").strip()
    exp_host = (expected_db_host or "").strip()

    if not exp_db or not exp_host:
        raise RuntimeError(
            "SAFETY REFUSAL: Expected staging database identity is not configured. "
            "Both --expected-db-name (or EXPECTED_STAGING_DB_NAME) and "
            "--expected-db-host (or EXPECTED_STAGING_DB_HOST) are strictly required "
            "to verify the target PostgreSQL database before seeding."
        )

    url = getattr(target_engine, "url", None)
    if not url:
        raise RuntimeError("SAFETY REFUSAL: Target database engine has no URL configured.")

    drivername = getattr(url, "drivername", "") or ""
    if not drivername.startswith("postgresql"):
        raise RuntimeError(
            f"SAFETY REFUSAL: Target database driver '{drivername}' is not a genuine PostgreSQL dialect."
        )

    resolved_db = (url.database or "").strip()
    resolved_host = (url.host or "").strip()

    if not resolved_db or not resolved_host:
        raise RuntimeError(
            "SAFETY REFUSAL: Target database name or host could not be resolved from engine URL. "
            "Execution aborted."
        )

    # Detect and refuse ambiguous URL formatting (query injection, path traversal, userinfo in host)
    if any(ch in resolved_db for ch in ["?", "#", "&", "\\", " "]):
        raise RuntimeError(
            f"SAFETY REFUSAL: Target database name contains ambiguous URL formatting characters: '{resolved_db}'"
        )
    if any(ch in resolved_host for ch in ["/", "?", "#", "@", " "]):
        raise RuntimeError(
            f"SAFETY REFUSAL: Target database host contains ambiguous URL formatting characters: '{resolved_host}'"
        )
    if any(ch in exp_db for ch in ["?", "#", "&", "\\", " "]):
        raise RuntimeError(
            f"SAFETY REFUSAL: Configured expected database name contains ambiguous characters: '{exp_db}'"
        )
    if any(ch in exp_host for ch in ["/", "?", "#", "@", " "]):
        raise RuntimeError(
            f"SAFETY REFUSAL: Configured expected database host contains ambiguous characters: '{exp_host}'"
        )

    clean_resolved_db = resolved_db.strip("/")
    clean_exp_db = exp_db.strip("/")

    if not clean_resolved_db or not clean_exp_db:
        raise RuntimeError("SAFETY REFUSAL: Database name cannot be empty or a bare slash.")

    forbidden_names = {"postgres", "template0", "template1", "defaultdb"}
    forbidden_terms = ("prod", "production", "live", "canonical")

    resolved_db_lower = clean_resolved_db.lower()
    resolved_host_lower = resolved_host.lower()
    exp_db_lower = clean_exp_db.lower()
    exp_host_lower = exp_host.lower()

    if resolved_db_lower in forbidden_names:
        raise RuntimeError(
            f"SAFETY REFUSAL: Target database '{clean_resolved_db}' is a protected system or default database. "
            "Execution aborted."
        )

    if any(t in resolved_db_lower for t in forbidden_terms) or any(t in resolved_host_lower for t in forbidden_terms):
        raise RuntimeError(
            f"SAFETY REFUSAL: Target database '{clean_resolved_db}' or host '{resolved_host}' matches "
            "prohibited production naming. Execution aborted to protect production environments."
        )

    if any(t in exp_db_lower for t in forbidden_terms) or any(t in exp_host_lower for t in forbidden_terms):
        raise RuntimeError(
            f"SAFETY REFUSAL: Configured expected database identity ('{clean_exp_db}' / '{exp_host}') "
            "matches prohibited production naming. Execution aborted."
        )

    if resolved_db_lower != exp_db_lower:
        raise RuntimeError(
            f"SAFETY REFUSAL: Database name mismatch. Resolved target database is '{clean_resolved_db}', "
            f"but expected staging database is '{clean_exp_db}'. Execution aborted."
        )

    norm_resolved_host = resolved_host_lower.split(":")[0].strip("[]")
    norm_expected_host = exp_host_lower.split(":")[0].strip("[]")

    if norm_resolved_host != norm_expected_host:
        raise RuntimeError(
            f"SAFETY REFUSAL: Database host mismatch. Resolved target host is '{norm_resolved_host}', "
            f"but expected staging host is '{norm_expected_host}'. Execution aborted."
        )

    return {
        "verified": True,
        "database": clean_resolved_db,
        "host": norm_resolved_host,
        "port": getattr(url, "port", None) or 5432,
    }


def verify_server_database_identity(db, expected_db_name: str) -> str:
    """Executes server catalog query to affirmatively verify active database session."""
    from sqlalchemy import text
    try:
        server_db = db.execute(text("SELECT current_database()")).scalar()
    except Exception as exc:
        clean_msg = sanitize_error_message(exc)
        raise RuntimeError(
            f"SAFETY REFUSAL: Failed to query server-side database identity: {clean_msg}"
        ) from None

    if not server_db:
        raise RuntimeError("SAFETY REFUSAL: Server returned an empty database name.")

    server_db_clean = server_db.strip().strip("/").lower()
    exp_db_clean = expected_db_name.strip().strip("/").lower()

    if server_db_clean != exp_db_clean:
        raise RuntimeError(
            f"SAFETY REFUSAL: Server-side database identity mismatch. "
            f"Connected server reports active database '{server_db_clean}', but expected staging database is '{exp_db_clean}'."
        )
    return server_db


def verify_staging_environment_guards(
    expected_db_name: Optional[str] = None,
    expected_db_host: Optional[str] = None,
) -> dict:
    """Fails closed if environment, dialect, or database identity fails safety policies."""
    normalized_env = (settings.APP_ENV or "").strip().lower()
    if normalized_env != "staging":
        raise RuntimeError(
            f"SAFETY REFUSAL: Staging demo seeding is restricted to APP_ENV='staging'. "
            f"Current environment is '{settings.APP_ENV}'. Execution aborted."
        )

    dialect = engine.dialect.name
    if dialect != "postgresql":
        raise RuntimeError(
            f"SAFETY REFUSAL: Staging demo seeding requires a genuine PostgreSQL database. "
            f"Current resolved dialect is '{dialect}'. Execution aborted."
        )

    return verify_staging_database_identity(
        target_engine=engine,
        expected_db_name=expected_db_name,
        expected_db_host=expected_db_host,
    )


def build_demo_hospital() -> Hospital:
    """Instantiates the single baseline hospital entity with explicit synthetic demo labeling."""
    return Hospital(
        id=DEMO_HOSPITAL_ID,
        name="City General Hospital",
        address="100 Emergency Care Boulevard (Synthetic Demo Facility)",
        city="Bengaluru",
        lat=12.9716,
        lng=77.5946,
        type="Level 1 Trauma Center (Synthetic Demo)",
        blood_bank_available=True,
        organ_transplant_center=True,
        emergency_bays=12,
        contact_number="+91-80-2222-0001",
        is_current_hospital=True,
    )


def build_demo_donors() -> List[Donor]:
    """Instantiates the three synthetic donor profiles with clearly fictional deterministic coordinates and synthetic demo labels."""
    return [
        Donor(
            id="D-DEMO-001",
            user_id=None,
            blood_group="O-",
            distance_km=2.8,
            eta_minutes=7,
            eligibility="eligible",
            eligibility_reason="Synthetic benchmark profile (Fictional Demo)",
            response_probability=92,
            reliability_score=95,
            reachability_score=90,
            ai_rank=1,
            status="available",
            location_consent_granted=False,
            last_donation_days=90,
            historical_acceptance_rate=95,
            contacted_at=None,
            responded_at=None,
            lat=12.9790,
            lng=77.5910,
            is_synthetic=True,
            data_provenance="synthetic_registry",
            simulated_coordinates=True,
        ),
        Donor(
            id="D-DEMO-002",
            user_id=None,
            blood_group="A+",
            distance_km=3.5,
            eta_minutes=9,
            eligibility="eligible",
            eligibility_reason="Synthetic benchmark profile (Fictional Demo)",
            response_probability=88,
            reliability_score=90,
            reachability_score=85,
            ai_rank=2,
            status="available",
            location_consent_granted=False,
            last_donation_days=60,
            historical_acceptance_rate=90,
            contacted_at=None,
            responded_at=None,
            lat=12.9680,
            lng=77.6020,
            is_synthetic=True,
            data_provenance="synthetic_registry",
            simulated_coordinates=True,
        ),
        Donor(
            id="D-DEMO-003",
            user_id=None,
            blood_group="O+",
            distance_km=4.2,
            eta_minutes=11,
            eligibility="eligible",
            eligibility_reason="Synthetic benchmark profile (Fictional Demo)",
            response_probability=85,
            reliability_score=88,
            reachability_score=82,
            ai_rank=3,
            status="available",
            location_consent_granted=False,
            last_donation_days=120,
            historical_acceptance_rate=88,
            contacted_at=None,
            responded_at=None,
            lat=12.9610,
            lng=77.5880,
            is_synthetic=True,
            data_provenance="synthetic_registry",
            simulated_coordinates=True,
        ),
    ]


def seed_staging_demo_data(args) -> dict:
    """Executes the guarded demo seeding workflow with sanitized error reporting."""
    expected_db_name = getattr(args, "expected_db_name", None)
    if not isinstance(expected_db_name, str):
        expected_db_name = None
    expected_db_host = getattr(args, "expected_db_host", None)
    if not isinstance(expected_db_host, str):
        expected_db_host = None

    # Step 1: Preflight guards
    verified_identity = verify_staging_environment_guards(
        expected_db_name=expected_db_name,
        expected_db_host=expected_db_host,
    )
    if verified_identity:
        logger.info(
            f"Target Database Identity POSITIVELY VERIFIED: host='{verified_identity['host']}', "
            f"database='{verified_identity['database']}'"
        )

    db = SessionLocal()
    try:
        # Step 2: Server-side database identity verification
        target_db = expected_db_name or (verified_identity.get("database") if isinstance(verified_identity, dict) else None)
        if target_db:
            verify_server_database_identity(db, target_db)

        # Step 3: Collision check across all intended records
        collisions = []

        existing_hospital = db.query(Hospital).filter(Hospital.id == DEMO_HOSPITAL_ID).first()
        if existing_hospital:
            collisions.append(f"Hospital(id='{existing_hospital.id}', name='{existing_hospital.name}')")

        existing_donors = db.query(Donor).filter(Donor.id.in_(DEMO_DONOR_IDS)).all()
        for d in existing_donors:
            collisions.append(f"Donor(id='{d.id}', blood_group='{d.blood_group}')")

        if collisions:
            collision_str = "; ".join(collisions)
            raise RuntimeError(
                f"COLLISION REFUSAL: Target database already contains matching demo record(s): [{collision_str}]. "
                "No records were modified or overwritten. Aborting."
            )

        # Step 4: Dry-Run Guard
        if not args.confirm:
            logger.info(
                "DRY-RUN COMPLETE: Target database verified and 0 ID collisions found. "
                "Zero records written because --confirm was omitted. "
                f"Intended seed: 1 Hospital ('{DEMO_HOSPITAL_ID}'), 3 Donors ({DEMO_DONOR_IDS})."
            )
            return {
                "status": "dry_run",
                "created": False,
                "hospital_id": DEMO_HOSPITAL_ID,
                "donor_ids": DEMO_DONOR_IDS,
            }

        # Step 5: Confirmed Write Transaction (1 Hospital + 3 Donors)
        hospital = build_demo_hospital()
        donors = build_demo_donors()

        db.add(hospital)
        for donor in donors:
            db.add(donor)

        db.flush()
        db.commit()

        logger.info(
            f"SUCCESS: Staging demo records committed: 1 Hospital ('{DEMO_HOSPITAL_ID}'), "
            f"3 Donors ({DEMO_DONOR_IDS})."
        )
        return {
            "status": "created",
            "created": True,
            "hospital_id": DEMO_HOSPITAL_ID,
            "donor_ids": DEMO_DONOR_IDS,
        }
    except Exception as exc:
        db.rollback()
        clean_msg = sanitize_error_message(exc)
        logger.error(f"Seeding error occurred. Transaction rolled back: {clean_msg}")
        raise RuntimeError(f"Seeding error occurred: {clean_msg}") from None
    finally:
        db.close()


def main():
    args = parse_arguments()
    try:
        result = seed_staging_demo_data(args)
        print("\n--- Staging Demo Seeding Summary ---")
        print(f"Status:         {result['status'].upper()} (Synthetic Demo Data)")
        print(f"Hospital Seeded:{result['hospital_id']} (City General Hospital - Synthetic Demo Facility)")
        print(f"Donors Seeded:  {', '.join(result['donor_ids'])} (Synthetic Registry Profiles)")
        print(f"Record Written: {result['created']}")
        print("------------------------------------\n")
        sys.exit(0)
    except Exception as e:
        clean_err = sanitize_error_message(e)
        print(f"\n[ERROR] Seeding failed: {clean_err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
