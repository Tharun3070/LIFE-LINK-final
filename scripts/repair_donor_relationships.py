"""
Idempotent Database Repair Script: Repair Persistent Donor -> User Relationships
File: backend/scripts/repair_donor_relationships.py

This script safely repairs the donor -> user relationship in the development SQLite database (lifelink.db).
Specifically:
- Verifies that target user 'usr-dnr-005' exists.
- Links primary universal donor 'D-101' to 'usr-dnr-005' if not already set.
- Unlinks 'D-104' from 'usr-dnr-005' if erroneously assigned, setting it to None.
- Preserves all other tables, rows, columns, audit logs, and existing data.
- Is strictly idempotent: running it multiple times makes no redundant changes.
"""

import sys
import os

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.db.session import SessionLocal
from app.models.user import User
from app.models.donor import Donor
from app.models.consent import Consent


def repair_donor_relationships(dry_run: bool = False) -> dict:
    db = SessionLocal()
    report = {
        "status": "success",
        "dry_run": dry_run,
        "rows_modified": 0,
        "details": [],
        "before_state": {},
        "after_state": {},
    }

    try:
        # 1. Validate that referenced user exists
        target_user = db.query(User).filter(User.id == "usr-dnr-005").first()
        if not target_user:
            report["status"] = "error"
            report["message"] = "Referenced user 'usr-dnr-005' does not exist in database. Aborting repair."
            return report

        # Verify user has donor role
        if target_user.role != "donor":
            report["status"] = "error"
            report["message"] = f"User 'usr-dnr-005' has role '{target_user.role}', expected 'donor'. Aborting."
            return report

        # Verify consent record exists for this user
        consent = db.query(Consent).filter(Consent.user_id == target_user.id).first()
        consent_status = "present" if consent else "missing"

        # 2. Inspect current donor states
        all_donors = db.query(Donor).all()
        for d in all_donors:
            report["before_state"][d.id] = d.user_id

        # 3. Apply safe, idempotent updates
        changes_to_apply = []

        # Target 1: D-101 must be linked to usr-dnr-005
        donor_101 = db.query(Donor).filter(Donor.id == "D-101").first()
        if donor_101:
            if donor_101.user_id != "usr-dnr-005":
                changes_to_apply.append({
                    "donor_id": "D-101",
                    "action": "assign_user_id",
                    "old_user_id": donor_101.user_id,
                    "new_user_id": "usr-dnr-005",
                })
                if not dry_run:
                    donor_101.user_id = "usr-dnr-005"
            else:
                report["details"].append("D-101 already linked to 'usr-dnr-005'. No change needed.")
        else:
            report["details"].append("Donor 'D-101' not found in database.")

        # Target 2: D-104 must not claim usr-dnr-005 (it is a registry donor without an app user)
        donor_104 = db.query(Donor).filter(Donor.id == "D-104").first()
        if donor_104:
            if donor_104.user_id == "usr-dnr-005":
                changes_to_apply.append({
                    "donor_id": "D-104",
                    "action": "clear_user_id",
                    "old_user_id": donor_104.user_id,
                    "new_user_id": None,
                })
                if not dry_run:
                    donor_104.user_id = None
            else:
                report["details"].append(f"D-104 user_id is '{donor_104.user_id}'. No change needed.")

        # 4. Commit if changes were made and not dry_run
        report["rows_modified"] = len(changes_to_apply)
        report["changes"] = changes_to_apply

        if changes_to_apply and not dry_run:
            db.commit()
            report["message"] = f"Successfully updated {len(changes_to_apply)} donor records."
        elif not changes_to_apply:
            report["message"] = "Database is already in desired state. 0 rows modified (idempotent)."
        else:
            report["message"] = f"Dry run complete. {len(changes_to_apply)} records would be updated."

        # 5. Record after-state
        for d in db.query(Donor).all():
            report["after_state"][d.id] = d.user_id

        report["user_verified"] = {
            "id": target_user.id,
            "email": target_user.email,
            "role": target_user.role,
            "consent_record": consent_status,
        }

    except Exception as e:
        db.rollback()
        report["status"] = "error"
        report["message"] = f"Exception occurred during repair: {str(e)}"
    finally:
        db.close()

    return report


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    res = repair_donor_relationships(dry_run=dry)
    import json
    print(json.dumps(res, indent=2))
