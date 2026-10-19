"""
LifeLink Synthetic Donor Dataset Importer
File: backend/scripts/import_donors_csv.py

Imports synthetic donor profiles from CSV (e.g., LifeLink_Realistic_Synthetic_30K_Donors.csv)
into the LifeLink database under strict clinical and data-integrity safeguards:
1. Hard Validation: Validates ABO/Rh blood groups, eligibility states, age, weight, and hemoglobin.
2. Idempotency: Repeated runs produce identical state without duplicate records or orphaned references.
3. Protected Relationships: Never modifies, overwrites, or disassociates existing user-linked donors.
4. Provenance & Safety: Marks all imported profiles as synthetic registry data (is_synthetic=True,
   data_provenance='synthetic_registry'). Precludes live SMS/email emergency dispatch alerts.
5. Location Honesty: Never invents random coordinates. If --simulate-coordinates is explicitly passed,
   marks coordinates as simulated. Missing coordinates remain explicitly unobserved.
6. Transparent History: Sets historical_acceptance_rate=0 to explicitly indicate unobserved dispatch history
   instead of fabricating an arbitrary 75% acceptance rate.
"""

import sys
import os
import argparse
import csv
import hashlib
from datetime import datetime, timezone, date
from typing import Dict, Any, List, Optional, Tuple

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.donor import Donor
from app.models.user import User

VALID_BLOOD_GROUPS = {"O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"}
VALID_AVAILABILITIES = {"Available", "On-call", "Unavailable"}
VALID_ELIGIBILITY = {"Yes", "No"}

# Reference coordinates for major Indian urban centers (used ONLY when --simulate-coordinates is set)
CITY_CENTERS: Dict[str, Tuple[float, float]] = {
    "Bengaluru": (12.9716, 77.5946),
    "Bangalore": (12.9716, 77.5946),
    "Mumbai": (19.0760, 72.8777),
    "Delhi": (28.6139, 77.2090),
    "New Delhi": (28.6139, 77.2090),
    "Chennai": (13.0827, 80.2707),
    "Hyderabad": (17.3850, 78.4867),
    "Kolkata": (22.5726, 88.3639),
    "Pune": (18.5204, 73.8567),
    "Ahmedabad": (23.0225, 72.5714),
    "Jaipur": (26.9124, 75.7873),
    "Lucknow": (26.8467, 80.9462),
    "Chandigarh": (30.7333, 76.7794),
    "Coimbatore": (11.0168, 76.9558),
    "Kochi": (9.9312, 76.2673),
    "Cochin": (9.9312, 76.2673),
    "Indore": (22.7196, 75.8577),
    "Bhopal": (23.2599, 77.4126),
    "Nagpur": (21.1458, 79.0882),
    "Patna": (25.5941, 85.1376),
    "Thiruvananthapuram": (8.5241, 76.9366),
    "Visakhapatnam": (17.6868, 83.2185),
    "Surat": (21.1702, 72.8311),
    "Vadodara": (22.3072, 73.1812),
}


def compute_simulated_coordinates(city: str, donor_id: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Computes deterministic simulated coordinates within ~5 km of the city center.
    Uses MD5 digest of donor_id for stable pseudo-random offsets (no non-deterministic RNG).
    """
    cleaned_city = (city or "").strip().title()
    center = CITY_CENTERS.get(cleaned_city)
    if not center:
        # Fallback to Bengaluru reference center if unknown Indian city
        center = CITY_CENTERS["Bengaluru"]

    lat_base, lng_base = center
    # Deterministic hash digest between -0.04 and +0.04 degrees (~4 km)
    h = hashlib.md5(f"{donor_id}:{cleaned_city}".encode("utf-8")).hexdigest()
    lat_offset = ((int(h[:4], 16) / 65535.0) - 0.5) * 0.08
    lng_offset = ((int(h[4:8], 16) / 65535.0) - 0.5) * 0.08

    return round(lat_base + lat_offset, 5), round(lng_base + lng_offset, 5)


def parse_last_donation_days(last_donation_date_str: Optional[str], ref_date: Optional[date] = None) -> Optional[int]:
    """
    Computes days elapsed since last donation date relative to reference date (2026-10-10).
    Robustly supports both ISO (%Y-%m-%d) and common regional formats (%d-%m-%Y, %d/%m/%Y).
    """
    if not last_donation_date_str or not last_donation_date_str.strip():
        return None
    raw = last_donation_date_str.strip()
    dt = None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(raw, fmt).date()
            break
        except ValueError:
            continue
    if dt is None:
        return None

    if ref_date is None:
        ref_date = date(2026, 10, 10)
    days = (ref_date - dt).days
    return max(0, days)


def validate_row(row: Dict[str, str], row_num: int) -> Tuple[bool, List[str]]:
    """Strict clinical and data validation of a CSV record."""
    errors = []
    donor_id = row.get("Donor_ID", "").strip()
    if not donor_id:
        errors.append(f"Row {row_num}: Missing Donor_ID")

    bg = row.get("Blood_Group", "").strip().upper()
    if bg not in VALID_BLOOD_GROUPS:
        errors.append(f"Row {row_num}: Invalid Blood_Group '{bg}'")

    elig = row.get("Eligible_for_Donation", "").strip()
    if elig not in VALID_ELIGIBILITY:
        errors.append(f"Row {row_num}: Invalid Eligible_for_Donation '{elig}'")

    avail = row.get("Availability", "").strip()
    if avail not in VALID_AVAILABILITIES:
        errors.append(f"Row {row_num}: Invalid Availability '{avail}'")

    # Age check
    try:
        age = int(row.get("Age", "0"))
        if not (18 <= age <= 65):
            errors.append(f"Row {row_num}: Age {age} outside legal donation range (18-65)")
    except ValueError:
        errors.append(f"Row {row_num}: Non-integer Age '{row.get('Age')}'")

    # Weight check
    try:
        wt = float(row.get("Weight_kg", "0"))
        if wt < 45.0:
            errors.append(f"Row {row_num}: Weight {wt} kg below minimum 45 kg threshold")
    except ValueError:
        errors.append(f"Row {row_num}: Non-float Weight_kg '{row.get('Weight_kg')}'")

    # Hemoglobin check
    try:
        hb = float(row.get("Hemoglobin_g_dL", "0"))
        if hb <= 0:
            errors.append(f"Row {row_num}: Non-positive Hemoglobin '{hb}'")
    except ValueError:
        errors.append(f"Row {row_num}: Non-float Hemoglobin_g_dL '{row.get('Hemoglobin_g_dL')}'")

    return (len(errors) == 0, errors)


def import_donors(
    csv_path: str,
    dry_run: bool = False,
    limit: Optional[int] = None,
    batch_size: int = 500,
    simulate_coordinates: bool = False,
    session: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Executes the validated, idempotent ingestion of synthetic donors.
    """
    start_time = datetime.now(timezone.utc)
    report = {
        "status": "success",
        "csv_path": csv_path,
        "dry_run": dry_run,
        "limit": limit,
        "simulate_coordinates": simulate_coordinates,
        "total_records_read": 0,
        "valid_records": 0,
        "invalid_records": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "protected_count": 0,
        "validation_errors": [],
        "execution_seconds": 0.0,
    }

    if not os.path.exists(csv_path):
        report["status"] = "error"
        report["message"] = f"CSV file not found: {csv_path}"
        return report

    own_session = False
    db = session
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        # Load existing donor IDs to enforce idempotency and protect existing relationships
        existing_donors: Dict[str, Donor] = {d.id: d for d in db.query(Donor).all()}

        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            row_num = 1
            batch: List[Donor] = []

            for row in reader:
                row_num += 1
                if limit and report["valid_records"] >= limit:
                    break

                report["total_records_read"] += 1
                is_valid, errors = validate_row(row, row_num)
                if not is_valid:
                    report["invalid_records"] += 1
                    report["validation_errors"].extend(errors[:3])
                    continue

                report["valid_records"] += 1
                donor_id = row["Donor_ID"].strip()
                blood_group = row["Blood_Group"].strip().upper()
                is_eligible = row["Eligible_for_Donation"].strip() == "Yes"
                eligibility_str = "eligible" if is_eligible else "ineligible"
                eligibility_reason = row.get("Eligibility_Reason", "").strip() or None

                raw_avail = row.get("Availability", "").strip()
                if not is_eligible:
                    status_str = "unavailable"
                elif raw_avail == "Available":
                    status_str = "available"
                elif raw_avail == "On-call":
                    status_str = "on-call"
                else:
                    status_str = "unavailable"

                days_since_donation = parse_last_donation_days(row.get("Last_Donation_Date"))

                # Coordinate determination
                if simulate_coordinates:
                    lat, lng = compute_simulated_coordinates(row.get("City", ""), donor_id)
                    is_sim_coords = True
                else:
                    lat, lng = None, None
                    is_sim_coords = False

                # Check existing record
                existing = existing_donors.get(donor_id)
                if existing:
                    # SAFETY GUARD: Protect user-linked donors or production records
                    if existing.user_id is not None or not existing.is_synthetic:
                        report["protected_count"] += 1
                        continue

                    # Idempotent update of synthetic record
                    if not dry_run:
                        existing.blood_group = blood_group
                        existing.eligibility = eligibility_str
                        existing.eligibility_reason = eligibility_reason
                        existing.status = status_str
                        existing.last_donation_days = days_since_donation
                        existing.lat = lat
                        existing.lng = lng
                        existing.simulated_coordinates = is_sim_coords
                        existing.is_synthetic = True
                        existing.data_provenance = "synthetic_registry"
                        # Explicit unobserved history (0 represents unobserved dispatch history)
                        existing.historical_acceptance_rate = 0
                    report["updated_count"] += 1
                else:
                    # New synthetic donor
                    new_donor = Donor(
                        id=donor_id,
                        user_id=None,
                        blood_group=blood_group,
                        distance_km=0.0,
                        eta_minutes=0,
                        eligibility=eligibility_str,
                        eligibility_reason=eligibility_reason,
                        response_probability=50,
                        reliability_score=50,
                        reachability_score=50,
                        ai_rank=999,
                        status=status_str,
                        location_consent_granted=False,
                        last_donation_days=days_since_donation,
                        historical_acceptance_rate=0,  # Unobserved history
                        contacted_at=None,
                        responded_at=None,
                        lat=lat,
                        lng=lng,
                        is_synthetic=True,
                        data_provenance="synthetic_registry",
                        simulated_coordinates=is_sim_coords,
                    )
                    report["inserted_count"] += 1
                    if not dry_run:
                        batch.append(new_donor)
                        if len(batch) >= batch_size:
                            db.add_all(batch)
                            db.commit()
                            batch = []

            # Flush final batch
            if not dry_run and batch:
                db.add_all(batch)
                db.commit()
                batch = []

    except Exception as e:
        if not dry_run:
            db.rollback()
        report["status"] = "error"
        report["message"] = str(e)
        return report
    finally:
        if own_session:
            db.close()

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    report["execution_seconds"] = round(duration, 3)
    return report


def main():
    parser = argparse.ArgumentParser(
        description="LifeLink Synthetic Donor Dataset Importer with Clinical Safety & Idempotency"
    )
    default_csv = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "LifeLink_Realistic_Synthetic_30K_Donors.csv")
    )
    parser.add_argument(
        "--csv-path",
        default=default_csv,
        help="Path to the synthetic donors CSV file (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform validation and report summary without committing database changes",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of valid records to import (useful for quick staging tests)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Database commit batch size (default: %(default)s)",
    )
    parser.add_argument(
        "--simulate-coordinates",
        action="store_true",
        help="Assign simulated city-center coordinates with deterministic offsets for testing (clearly marked)",
    )

    args = parser.parse_args()

    print(f"=== LifeLink Synthetic Donor Importer ===")
    print(f"CSV Path:              {args.csv_path}")
    print(f"Dry Run:               {args.dry_run}")
    print(f"Limit:                 {args.limit or 'All rows'}")
    print(f"Simulate Coordinates:  {args.simulate_coordinates}")
    print(f"Batch Size:            {args.batch_size}")
    print("------------------------------------------")

    result = import_donors(
        csv_path=args.csv_path,
        dry_run=args.dry_run,
        limit=args.limit,
        batch_size=args.batch_size,
        simulate_coordinates=args.simulate_coordinates,
    )

    print(f"Status:                {result.get('status')}")
    print(f"Records Read:          {result.get('total_records_read')}")
    print(f"Valid Records:         {result.get('valid_records')}")
    print(f"Invalid Records:       {result.get('invalid_records')}")
    print(f"Inserted:              {result.get('inserted_count')}")
    print(f"Updated:               {result.get('updated_count')}")
    print(f"Protected (Skipped):   {result.get('protected_count')}")
    print(f"Elapsed Time:          {result.get('execution_seconds')}s")

    if result.get("validation_errors"):
        print("\nSample Validation Errors:")
        for err in result["validation_errors"][:5]:
            print(f"  - {err}")

    if result.get("status") == "error":
        print(f"\nERROR: {result.get('message')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
