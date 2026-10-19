"""
LifeLink Phase 3.1: Safe Canonical Alembic Alignment Script
File: backend/scripts/execute_phase31_alembic_alignment.py
"""
import sys
import os
import sqlite3
import hashlib
from typing import Dict, Any

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROOT_DIR = os.path.abspath(os.path.join(BACKEND_DIR, ".."))

CANONICAL_DB = os.path.join(BACKEND_DIR, "lifelink.db")
BACKUP_DB = os.path.join(BACKEND_DIR, "lifelink_backup_pre_phase31_alembic_alignment.db")
ROOT_LEGACY_DB = os.path.join(ROOT_DIR, "lifelink.db")

def get_file_md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def execute_alignment():
    print("=" * 80)
    print("LIFELINK PHASE 3.1 — CANONICAL DATABASE ALEMBIC ALIGNMENT")
    print("=" * 80)

    # 1. Re-verify canonical absolute path
    print(f"\n[Step 1] Target Canonical Database: {CANONICAL_DB}")
    assert os.path.exists(CANONICAL_DB), f"Canonical DB does not exist at {CANONICAL_DB}"
    canonical_size_before = os.path.getsize(CANONICAL_DB)
    print(f"Canonical DB file size: {canonical_size_before} bytes")

    # Record root legacy DB state to prove it remains untouched
    assert os.path.exists(ROOT_LEGACY_DB), f"Root legacy DB missing at {ROOT_LEGACY_DB}"
    root_legacy_size_before = os.path.getsize(ROOT_LEGACY_DB)
    root_legacy_md5_before = get_file_md5(ROOT_LEGACY_DB)
    print(f"Root legacy DB recorded: {ROOT_LEGACY_DB} ({root_legacy_size_before} bytes, MD5: {root_legacy_md5_before})")

    # Connect to canonical database for pre-change census
    conn = sqlite3.connect(CANONICAL_DB)
    c = conn.cursor()

    # Pre-change integrity check
    integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
    assert integrity == "ok", f"Precondition failed: integrity_check returned '{integrity}'"

    fk_violations = c.execute("PRAGMA foreign_key_check").fetchall()
    assert len(fk_violations) == 0, f"Precondition failed: FK violations found: {fk_violations}"

    current_ver = c.execute("SELECT version_num FROM alembic_version").fetchall()
    assert current_ver == [("0002_donor_emergency_interaction",)], f"Precondition failed: version is {current_ver}"

    cols = [col[1] for col in c.execute("PRAGMA table_info(donors)").fetchall()]
    assert "is_synthetic" in cols, "Precondition failed: is_synthetic column missing"
    assert "data_provenance" in cols, "Precondition failed: data_provenance column missing"
    assert "simulated_coordinates" in cols, "Precondition failed: simulated_coordinates column missing"

    existing_index = c.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='ix_donors_is_synthetic'").fetchone()
    assert existing_index is None, "Precondition failed: ix_donors_is_synthetic index already exists"

    # Pre-change table census
    table_census_before: Dict[str, int] = {}
    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
    for t in sorted(tables):
        count = c.execute(f"SELECT count(*) FROM \"{t}\"").fetchone()[0]
        table_census_before[t] = count

    print("\nPre-Change Census Verified:")
    print(f"  Alembic version: {current_ver[0][0]}")
    print(f"  Target columns confirmed on 'donors': is_synthetic, data_provenance, simulated_coordinates")
    print(f"  Missing index confirmed: ix_donors_is_synthetic")
    print(f"  Table row counts: {table_census_before}")

    conn.close()

    # 2. Atomic Backup via SQLite Online Backup API
    print(f"\n[Step 2] Creating Online Backup: {BACKUP_DB}")
    if os.path.exists(BACKUP_DB):
        os.remove(BACKUP_DB)

    src_conn = sqlite3.connect(CANONICAL_DB)
    bck_conn = sqlite3.connect(BACKUP_DB)
    src_conn.backup(bck_conn)
    src_conn.close()
    bck_conn.close()

    backup_size = os.path.getsize(BACKUP_DB)
    print(f"Backup created successfully. File size: {backup_size} bytes")

    # Verify backup integrity and table counts
    v_bck = sqlite3.connect(BACKUP_DB)
    v_c = v_bck.cursor()
    bck_integrity = v_c.execute("PRAGMA integrity_check").fetchone()[0]
    assert bck_integrity == "ok", f"Backup verification failed: integrity_check='{bck_integrity}'"

    bck_census: Dict[str, int] = {}
    for t in sorted(tables):
        bck_census[t] = v_c.execute(f"SELECT count(*) FROM \"{t}\"").fetchone()[0]
    assert bck_census == table_census_before, f"Backup census mismatch: {bck_census} vs {table_census_before}"
    v_bck.close()
    print("Backup integrity check 'ok' and 100% row-count parity confirmed.")

    # 3. Controlled Atomic Repair Transaction
    print("\n[Step 3] Executing Atomic Alignment Transaction on Canonical Database...")
    exec_conn = sqlite3.connect(CANONICAL_DB)
    exec_c = exec_conn.cursor()

    try:
        exec_c.execute("BEGIN IMMEDIATE")
        
        # 1. Create index ix_donors_is_synthetic
        exec_c.execute("CREATE INDEX ix_donors_is_synthetic ON donors (is_synthetic)")
        print("  - Executed: CREATE INDEX ix_donors_is_synthetic ON donors (is_synthetic)")

        # 2. Conditional version update requiring exactly 1 row
        update_res = exec_c.execute(
            "UPDATE alembic_version SET version_num = '0003_donor_synthetic_provenance' "
            "WHERE version_num = '0002_donor_emergency_interaction'"
        )
        if update_res.rowcount != 1:
            raise RuntimeError(f"Conditional update failed: expected 1 row affected, got {update_res.rowcount}")
        print(f"  - Executed: UPDATE alembic_version (affected rows: {update_res.rowcount})")

        exec_conn.commit()
        print("Alignment transaction COMMITTED successfully.")
    except Exception as e:
        exec_conn.rollback()
        exec_conn.close()
        print(f"CRITICAL ERROR: Transaction failed, rolled back! Error: {e}")
        # Restore backup
        import shutil
        shutil.copyfile(BACKUP_DB, CANONICAL_DB)
        print("Database restored from backup.")
        raise
    finally:
        exec_conn.close()

    # 4. Post-Commit Verification
    print("\n[Step 4] Post-Commit Verification on Canonical Database...")
    post_conn = sqlite3.connect(CANONICAL_DB)
    post_c = post_conn.cursor()

    post_integrity = post_c.execute("PRAGMA integrity_check").fetchone()[0]
    assert post_integrity == "ok", f"Post-check failed: integrity={post_integrity}"

    post_fk = post_c.execute("PRAGMA foreign_key_check").fetchall()
    assert len(post_fk) == 0, f"Post-check failed: FK violations={post_fk}"

    new_ver = post_c.execute("SELECT version_num FROM alembic_version").fetchall()
    assert new_ver == [("0003_donor_synthetic_provenance",)], f"Post-check failed: version={new_ver}"

    idx_entry = post_c.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name='ix_donors_is_synthetic'").fetchone()
    assert idx_entry is not None, "Post-check failed: ix_donors_is_synthetic not in sqlite_master"
    print(f"Verified Index SQL: {idx_entry[0]}")

    table_census_after: Dict[str, int] = {}
    for t in sorted(tables):
        table_census_after[t] = post_c.execute(f"SELECT count(*) FROM \"{t}\"").fetchone()[0]
    assert table_census_after == table_census_before, f"Row counts changed! {table_census_before} vs {table_census_after}"
    print(f"Verified Row-Count Parity across all {len(tables)} tables: {table_census_after}")

    post_conn.close()

    # 5. Verify root legacy database is untouched
    root_legacy_size_after = os.path.getsize(ROOT_LEGACY_DB)
    root_legacy_md5_after = get_file_md5(ROOT_LEGACY_DB)
    assert root_legacy_size_before == root_legacy_size_after, "Root legacy DB size changed!"
    assert root_legacy_md5_before == root_legacy_md5_after, "Root legacy DB MD5 changed!"
    print(f"Root Legacy Database Verification: UNTOUCHED (MD5: {root_legacy_md5_after})")

    # 6. Alembic Current & Migration Head Verification
    print("\n[Step 5] Alembic Migration State Verification...")
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    command.current(alembic_cfg, verbose=True)

    print("\n" + "=" * 80)
    print("PHASE 3.1 EXECUTION COMPLETE — 100% VERIFIED WITH ZERO REGRESSIONS")
    print("=" * 80)

if __name__ == "__main__":
    execute_alignment()
