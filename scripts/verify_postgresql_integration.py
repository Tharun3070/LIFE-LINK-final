"""
LifeLink — Automated PostgreSQL Integration Verification Runner (Priority 4).

Usage:
    # 1. Using environment variable:
    $env:LIFELINK_POSTGRES_TEST_URL="postgresql+psycopg://test_user:test_password@localhost:5432/lifelink_disposable_test"
    python scripts/verify_postgresql_integration.py

    # 2. Or using command-line argument:
    python scripts/verify_postgresql_integration.py --url "postgresql+psycopg://test_user:test_password@localhost:5432/lifelink_disposable_test"

SAFETY GUARANTEES:
- Strictly checks that the database target is PostgreSQL and contains a test identifier ('test', 'disposable', 'sandbox', 'ci').
- Refuses to run against production, system, canonical SQLite, or legacy SQLite databases.
- Redacts all credentials in output.
- Disables external Twilio live communications.
"""
import os
import sys
import argparse
import subprocess
from sqlalchemy import create_engine, text

# Add backend root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings, verify_isolated_postgresql_test_target


def main():
    parser = argparse.ArgumentParser(description="LifeLink PostgreSQL Integration Test Runner")
    parser.add_argument("--url", default=None, help="PostgreSQL test database URL (e.g. postgresql+psycopg://user:pass@localhost:5432/lifelink_test)")
    args = parser.parse_args()

    test_url = args.url or os.environ.get("LIFELINK_POSTGRES_TEST_URL") or os.environ.get("POSTGRES_TEST_DATABASE_URL")

    print("=" * 80)
    print(" LifeLink — PostgreSQL Production Integration Verification Runner")
    print("=" * 80)

    if not test_url:
        print("\n[!] STATUS: NO POSTGRESQL TEST TARGET CONFIGURED")
        print("\nTo execute live integration verification against an isolated PostgreSQL instance:")
        print("  1. Launch a disposable PostgreSQL instance:")
        print("     docker run --name lifelink-pg-test -e POSTGRES_PASSWORD=secret -e POSTGRES_DB=lifelink_test -p 5432:5432 -d postgres:16-alpine")
        print("  2. Set the environment variable and re-run:")
        print("     $env:LIFELINK_POSTGRES_TEST_URL='postgresql+psycopg://postgres:secret@localhost:5432/lifelink_test'")
        print("     python scripts/verify_postgresql_integration.py\n")
        sys.exit(2)

    # 1. Execute strict safety guard
    print("\n[Phase 1] Executing Database Safety Guard...")
    try:
        info = verify_isolated_postgresql_test_target(test_url)
        print(f"  [+] Target Dialect:    {info['dialect']}")
        print(f"  [+] Target Database:   {info['database']}")
        print(f"  [+] Target Host:       {info['host']}:{info['port']}")
        print(f"  [+] Sanitized Target:  {info['sanitized_target']}")
        print("  [+] Safety Check:      PASSED (Target positively identified as isolated test database)")
    except Exception as exc:
        print(f"\n[X] SAFETY GUARD REJECTION: {exc}")
        print("Aborting. No database actions were performed.")
        sys.exit(1)

    # 2. Test Network Connectivity
    print("\n[Phase 2] Testing Database Connectivity & Handshake...")
    normalized_url = settings.normalize_database_url(test_url)
    try:
        engine = create_engine(normalized_url, pool_pre_ping=True)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();")).scalar()
            print(f"  [+] Connection Successful! Server: {result[:50]}...")
        engine.dispose()
    except Exception as exc:
        print(f"  [X] Connection Failed to {info['sanitized_target']}: {exc}")
        print("\nPlease ensure the PostgreSQL server is running and reachable.")
        sys.exit(1)

    # 3. Set environment variable for pytest suite
    os.environ["LIFELINK_POSTGRES_TEST_URL"] = test_url
    os.environ["DATABASE_URL"] = normalized_url
    os.environ["TWILIO_LIVE_ENABLED"] = "False"
    os.environ["MOCK_NOTIFICATIONS_ONLY"] = "True"

    # 4. Run Pytest Integration Suite
    print("\n[Phase 3] Running Pytest Live PostgreSQL Integration Suite...")
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_postgresql_live_integration.py",
        "-v",
        "--tb=short"
    ]
    result = subprocess.run(cmd, cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

    if result.returncode == 0:
        print("\n" + "=" * 80)
        print(" [PASS] POSTGRESQL INTEGRATION VERIFICATION: ALL TESTS PASSED")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print(f" [FAIL] POSTGRESQL INTEGRATION VERIFICATION FAILED (Exit Code {result.returncode})")
        print("=" * 80)

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
