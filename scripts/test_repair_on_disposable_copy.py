"""
Test Alembic 0003 Reconciliation on Disposable Database Copy
File: backend/scripts/test_repair_on_disposable_copy.py
"""
import sys
import os
import sqlite3

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CANONICAL_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lifelink.db"))
DISPOSABLE_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lifelink_disposable_test.db"))

def run_test():
    print("=== Step B.5: Testing Repair on Disposable Copy ===")
    print(f"Canonical source:  {CANONICAL_DB}")
    print(f"Disposable target: {DISPOSABLE_DB}")

    # 1. Ensure clean slate
    if os.path.exists(DISPOSABLE_DB):
        os.remove(DISPOSABLE_DB)

    # 2. Atomic backup from canonical DB to disposable DB using SQLite Online Backup API
    src_conn = sqlite3.connect(CANONICAL_DB)
    dst_conn = sqlite3.connect(DISPOSABLE_DB)
    src_conn.backup(dst_conn)
    src_conn.close()
    dst_conn.close()

    print(f"Disposable copy created. Size: {os.path.getsize(DISPOSABLE_DB)} bytes")

    # 3. Precondition verification on disposable copy
    conn = sqlite3.connect(DISPOSABLE_DB)
    c = conn.cursor()

    integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
    assert integrity == "ok", f"Integrity check failed: {integrity}"

    current_ver = c.execute("SELECT version_num FROM alembic_version").fetchall()
    assert current_ver == [("0002_donor_emergency_interaction",)], f"Unexpected version: {current_ver}"

    cols = [col[1] for col in c.execute("PRAGMA table_info(donors)").fetchall()]
    assert "is_synthetic" in cols
    assert "data_provenance" in cols
    assert "simulated_coordinates" in cols

    idx_exists = c.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='ix_donors_is_synthetic'").fetchone()
    assert idx_exists is None, "Index already exists!"

    table_counts_before = {}
    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
    for t in tables:
        table_counts_before[t] = c.execute(f"SELECT count(*) FROM {t}").fetchone()[0]

    print("Preconditions verified successfully:")
    print(f"  - Version: {current_ver[0][0]}")
    print(f"  - Columns present: is_synthetic, data_provenance, simulated_coordinates")
    print(f"  - Index missing: ix_donors_is_synthetic")
    print(f"  - Table counts: {table_counts_before}")

    # 4. Execute the repair inside an explicit transaction
    print("\nExecuting repair transaction...")
    c.execute("BEGIN IMMEDIATE")
    c.execute("CREATE INDEX ix_donors_is_synthetic ON donors (is_synthetic)")
    res = c.execute("UPDATE alembic_version SET version_num = '0003_donor_synthetic_provenance' WHERE version_num = '0002_donor_emergency_interaction'")
    assert res.rowcount == 1, f"Expected 1 updated row, got {res.rowcount}"
    conn.commit()
    print("Transaction committed.")

    # 5. Postcondition verification
    post_integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
    assert post_integrity == "ok", f"Post integrity check failed: {post_integrity}"

    post_fk = c.execute("PRAGMA foreign_key_check").fetchall()
    assert len(post_fk) == 0, f"FK violations: {post_fk}"

    new_ver = c.execute("SELECT version_num FROM alembic_version").fetchall()
    assert new_ver == [("0003_donor_synthetic_provenance",)], f"Unexpected post version: {new_ver}"

    idx_info = c.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name='ix_donors_is_synthetic'").fetchone()
    assert idx_info is not None, "Index not found in sqlite_master!"
    print(f"Created index SQL: {idx_info[0]}")

    table_counts_after = {}
    for t in tables:
        table_counts_after[t] = c.execute(f"SELECT count(*) FROM {t}").fetchone()[0]

    assert table_counts_before == table_counts_after, f"Row counts changed! {table_counts_before} vs {table_counts_after}"
    print(f"Row count parity verified: all {len(tables)} tables preserved.")

    conn.close()

    # 6. Test Alembic against the disposable database
    print("\nVerifying Alembic recognizes the disposable database at head...")
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    norm_disp = DISPOSABLE_DB.replace("\\", "/")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{norm_disp}")

    command.current(alembic_cfg, verbose=True)

    print("\n=== All assertions passed on disposable copy! ===")

if __name__ == "__main__":
    run_test()
