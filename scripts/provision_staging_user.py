#!/usr/bin/env python3
"""
LifeLink Emergency Intelligence — Staging User Provisioning Utility
File: scripts/provision_staging_user.py

Provisions exactly ONE dedicated staging test account to facilitate authenticated
integration testing without triggering bulk demo-account seeding or weakening staging guards.

Strict Safety Guards:
1. Fails closed unless APP_ENV is explicitly 'staging'.
2. Refuses to write to any database unless --confirm flag is provided.
3. Positively verifies PostgreSQL dialect for non-mock runs.
4. Prevents duplicate user creation (idempotent duplicate checks).
5. Masks all credentials, passwords, and connection strings from output.
6. Executes inside a single transaction with automatic rollback on error.
"""

import os
import sys
import uuid
import getpass
import argparse
from datetime import datetime, timezone
import json
from typing import Optional, Dict, Any

# Ensure backend root is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.config import settings
from app.core.logging import logger
from app.core.security import get_password_hash
from app.core.permissions import UserRole
from app.db.session import SessionLocal, engine
from app.models.user import User
from app.models.consent import Consent
from app.models.audit import AuditLog
from app.models.hospital import Hospital


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Safely provision a single dedicated staging test user for LifeLink.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Explicit authorization flag. Changes will ONLY be committed if this flag is present.",
    )
    parser.add_argument(
        "--email",
        type=str,
        default="staging.doctor@lifelink.internal",
        help="Email address for the staging user.",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="Staging Emergency Doctor",
        help="Full display name for the user.",
    )
    parser.add_argument(
        "--role",
        type=str,
        default=UserRole.DOCTOR.value,
        choices=[r.value for r in UserRole],
        help="User role matching actual LifeLink UserRole definitions.",
    )
    parser.add_argument(
        "--role-title",
        type=str,
        default="Attending Emergency Physician",
        help="Professional clinical or operational title.",
    )
    parser.add_argument(
        "--user-id",
        type=str,
        default=None,
        help="Custom user ID. If omitted, generates a unique ID prefixed with 'usr-staging-'.",
    )
    parser.add_argument(
        "--hospital-id",
        type=str,
        default=None,
        help="Optional hospital ID. If omitted or not found, sets hospital_id to None for FK safety.",
    )
    parser.add_argument(
        "--password-env",
        type=str,
        default="STAGING_USER_PASSWORD",
        help="Name of environment variable containing the password. If unset, prompts securely.",
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
    """
    Positively verifies that the target PostgreSQL engine matches the explicitly
    configured staging database identity before any connection or transaction.

    Rules:
    1. Both expected_db_name and expected_db_host must be explicitly provided.
    2. Prohibits any production, canonical, or system database naming.
    3. Performs exact database-name matching (case-insensitive).
    4. Performs exact host matching (normalizing port separation, case-insensitive).
    5. Fails closed on any missing, malformed, or mismatched parameters.
    6. Ensures zero credential exposure in error messages.
    """
    exp_db = (expected_db_name or "").strip()
    exp_host = (expected_db_host or "").strip()

    if not exp_db or not exp_host:
        raise RuntimeError(
            "SAFETY REFUSAL: Expected staging database identity is not configured. "
            "Both --expected-db-name (or EXPECTED_STAGING_DB_NAME) and "
            "--expected-db-host (or EXPECTED_STAGING_DB_HOST) are strictly required "
            "to verify the target PostgreSQL database before provisioning."
        )

    # Resolve target database identity from engine URL
    url = getattr(target_engine, "url", None)
    if not url:
        raise RuntimeError("SAFETY REFUSAL: Target database engine has no URL configured.")

    resolved_db = (url.database or "").strip()
    resolved_host = (url.host or "").strip()

    if not resolved_db or not resolved_host:
        raise RuntimeError(
            "SAFETY REFUSAL: Target database name or host could not be resolved from engine URL. "
            "Execution aborted."
        )

    # 1. Prohibited production and system target checks
    forbidden_names = {"postgres", "template0", "template1", "defaultdb"}
    forbidden_terms = ("prod", "production", "live", "canonical")

    resolved_db_lower = resolved_db.lower()
    resolved_host_lower = resolved_host.lower()
    exp_db_lower = exp_db.lower()
    exp_host_lower = exp_host.lower()

    if resolved_db_lower in forbidden_names:
        raise RuntimeError(
            f"SAFETY REFUSAL: Target database '{resolved_db}' is a protected system or default database. "
            "Execution aborted."
        )

    if any(t in resolved_db_lower for t in forbidden_terms) or any(t in resolved_host_lower for t in forbidden_terms):
        raise RuntimeError(
            f"SAFETY REFUSAL: Target database '{resolved_db}' or host '{resolved_host}' matches "
            "prohibited production naming. Execution aborted to protect production environments."
        )

    if any(t in exp_db_lower for t in forbidden_terms) or any(t in exp_host_lower for t in forbidden_terms):
        raise RuntimeError(
            f"SAFETY REFUSAL: Configured expected database identity ('{exp_db}' / '{exp_host}') "
            "matches prohibited production naming. Execution aborted."
        )

    # 2. Exact database name match
    if resolved_db_lower != exp_db_lower:
        raise RuntimeError(
            f"SAFETY REFUSAL: Database name mismatch. Resolved target database is '{resolved_db}', "
            f"but expected staging database is '{exp_db}'. Execution aborted."
        )

    # 3. Exact host match (normalized without port)
    norm_resolved_host = resolved_host_lower.split(":")[0].strip()
    norm_expected_host = exp_host_lower.split(":")[0].strip()

    if norm_resolved_host != norm_expected_host:
        raise RuntimeError(
            f"SAFETY REFUSAL: Database host mismatch. Resolved target host is '{norm_resolved_host}', "
            f"but expected staging host is '{norm_expected_host}'. Execution aborted."
        )

    return {
        "verified": True,
        "database": resolved_db,
        "host": norm_resolved_host,
        "port": getattr(url, "port", None) or 5432,
    }


def verify_server_database_identity(db, expected_db_name: str) -> str:
    """
    Executes a server-side catalog query to affirmatively verify that the active database session
    is connected to the expected staging database catalog before any write transaction.
    """
    from sqlalchemy import text
    try:
        server_db = db.execute(text("SELECT current_database()")).scalar()
    except Exception as exc:
        raise RuntimeError(
            f"SAFETY REFUSAL: Failed to query server-side database identity: {exc}"
        ) from exc

    if not server_db:
        raise RuntimeError("SAFETY REFUSAL: Server returned an empty database name.")

    if server_db.strip().lower() != expected_db_name.strip().lower():
        raise RuntimeError(
            f"SAFETY REFUSAL: Server-side database identity mismatch. "
            f"Connected server reports active database '{server_db}', but expected staging database is '{expected_db_name}'."
        )
    return server_db


def verify_staging_environment_guards(
    expected_db_name: Optional[str] = None,
    expected_db_host: Optional[str] = None,
) -> dict:
    """Fails closed if environment, dialect, or database identity fails safety policies."""
    # 1. APP_ENV Guard
    normalized_env = (settings.APP_ENV or "").strip().lower()
    if normalized_env != "staging":
        raise RuntimeError(
            f"SAFETY REFUSAL: Staging provisioning is restricted to APP_ENV='staging'. "
            f"Current environment is '{settings.APP_ENV}'. Execution aborted."
        )

    # 2. Database Dialect Guard
    dialect = engine.dialect.name
    if dialect != "postgresql":
        raise RuntimeError(
            f"SAFETY REFUSAL: Staging provisioning requires a genuine PostgreSQL database. "
            f"Current resolved dialect is '{dialect}'. Execution aborted."
        )

    # 3. Positive Staging Database Identity Guard
    return verify_staging_database_identity(
        target_engine=engine,
        expected_db_name=expected_db_name,
        expected_db_host=expected_db_host,
    )


def get_staging_password(password_env_var: str) -> str:
    """Retrieves password from environment or secure prompt without echoing."""
    pwd = os.environ.get(password_env_var, "").strip()
    if not pwd:
        # Prompt interactively if available
        if sys.stdin.isatty():
            pwd = getpass.getpass(f"Enter password for staging user ({password_env_var} not set): ").strip()
        else:
            raise ValueError(
                f"Password error: Environment variable '{password_env_var}' is empty and "
                "no interactive terminal is available to prompt."
            )

    if len(pwd) < 8:
        raise ValueError("Password policy: Staging test account password must be at least 8 characters long.")
    return pwd


def provision_staging_user(args) -> dict:
    """Executes the controlled provisioning flow with strictly guarded execution order."""
    # Step 1: Preflight guards (environment, dialect, database identity)
    expected_db_name = getattr(args, "expected_db_name", None)
    if not isinstance(expected_db_name, str):
        expected_db_name = None
    expected_db_host = getattr(args, "expected_db_host", None)
    if not isinstance(expected_db_host, str):
        expected_db_host = None

    verified_identity = verify_staging_environment_guards(
        expected_db_name=expected_db_name,
        expected_db_host=expected_db_host,
    )
    if verified_identity:
        logger.info(
            f"Target Database Identity POSITIVELY VERIFIED: host='{verified_identity['host']}', "
            f"database='{verified_identity['database']}'"
        )

    # Step 2: Validate Role & Arguments
    valid_roles = [r.value for r in UserRole]
    if args.role not in valid_roles:
        raise ValueError(f"Invalid role '{args.role}'. Must be one of: {', '.join(valid_roles)}")

    email = args.email.strip().lower()
    user_id = args.user_id.strip() if args.user_id else f"usr-staging-{uuid.uuid4().hex[:10]}"
    display_name = args.name.strip()

    # Step 3: Check sanitized database target
    db_info = settings.get_sanitized_database_info()
    logger.info(f"Target Database Target: dialect={db_info['dialect']}, target={db_info['resolved_target']}")

    db = SessionLocal()
    try:
        # Step 4: Server-Side Active Database Identity Verification
        # Asserts connected session is physically attached to the expected catalog
        if expected_db_name:
            verify_server_database_identity(db, expected_db_name)

        # Step 5: Idempotent duplicate check (No password requested)
        existing = db.query(User).filter((User.id == user_id) | (User.email == email)).first()
        if existing:
            logger.info(
                f"IDEMPOTENCY NOTICE: User already exists (id='{existing.id}', email='{existing.email}'). "
                "No records modified."
            )
            return {
                "status": "already_exists",
                "user_id": existing.id,
                "email": existing.email,
                "role": existing.role,
                "created": False,
            }

        # Step 6: Hospital validation (No password requested)
        resolved_hospital_id = None
        resolved_hospital_name = "LifeLink Emergency Medical Center (Staging)"
        if args.hospital_id:
            hosp = db.query(Hospital).filter(Hospital.id == args.hospital_id.strip()).first()
            if hosp:
                resolved_hospital_id = hosp.id
                resolved_hospital_name = hosp.name
            else:
                logger.warning(
                    f"Hospital ID '{args.hospital_id}' not found in database. "
                    "Setting hospital_id=None for foreign-key safety."
                )

        # Step 7: Confirmation Guard (Dry-run completes WITHOUT requesting password or computing Bcrypt hash)
        if not args.confirm:
            logger.info(
                "DRY-RUN COMPLETE: Staging user verified but NOT committed because --confirm flag was omitted. "
                f"Proposed User: id='{user_id}', email='{email}', role='{args.role}'. "
                "To execute database write, re-run with --confirm."
            )
            return {
                "status": "dry_run",
                "user_id": user_id,
                "email": email,
                "role": args.role,
                "created": False,
            }

        # Step 8: Collect credentials and compute hash ONLY after confirmation and duplicate clearance
        password = get_staging_password(args.password_env)
        hashed_pwd = get_password_hash(password)

        now_utc = datetime.now(timezone.utc)
        now_iso = now_utc.isoformat()

        # Step 9: Build single User model
        new_user = User(
            id=user_id,
            name=display_name,
            email=email,
            hashed_password=hashed_pwd,
            role=args.role,
            role_title=args.role_title,
            hospital_id=resolved_hospital_id,
            hospital_name=resolved_hospital_name,
            organization="LifeLink Healthcare Staging Network",
            avatar=None,
            is_verified=True,
            last_login=None,
            session_status="active",
            created_at=now_utc,
        )

        # Step 10: Build accompanying Consent record (Explicit Opt-Out / Non-Consented state)
        new_consent = Consent(
            id=f"cns-staging-{uuid.uuid4().hex[:10]}",
            user_id=user_id,
            live_location=False,
            emergency_communication=False,
            donation_requests=False,
            health_data_sharing=False,
            updated_at=now_iso,
        )

        # Step 11: Build Audit Log record
        audit_record = AuditLog(
            id=f"audit-prov-{uuid.uuid4().hex[:10]}",
            timestamp=now_iso,
            actor="staging-user-provisioner",
            actor_type="system",
            action=f"Provisioned dedicated staging user ({args.role}) with explicit communication opt-out",
            resource="User",
            resource_id=user_id,
            authorization="staging_admin_provisioner",
            status="success",
            module="auth",
            metadata_json=json.dumps({
                "email": email,
                "role": args.role,
                "user_id": user_id,
                "consent_policy": "explicit_opt_out",
                "emergency_communication": False,
                "donation_requests": False,
            }),
        )

        # Step 12: Atomic Transaction Commit
        db.add(new_user)
        db.add(new_consent)
        db.add(audit_record)
        db.commit()

        logger.info(f"SUCCESS: Staging user successfully provisioned: id='{user_id}', email='{email}', role='{args.role}'.")
        return {
            "status": "created",
            "user_id": user_id,
            "email": email,
            "role": args.role,
            "created": True,
        }
    except Exception as exc:
        db.rollback()
        logger.error(f"Provisioning error occurred. Transaction rolled back: {exc}")
        raise
    finally:
        db.close()


def main():
    args = parse_arguments()
    try:
        result = provision_staging_user(args)
        # Print safe summary without exposing sensitive credentials
        print("\n--- Provisioning Operation Summary ---")
        print(f"Status:        {result['status'].upper()}")
        print(f"User ID:       {result['user_id']}")
        print(f"Email:         {result['email']}")
        print(f"Role:          {result['role']}")
        print(f"Record Written:{result['created']}")
        print("--------------------------------------\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Provisioning failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
