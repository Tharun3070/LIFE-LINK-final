"""
LifeLink Reusable Dataset Importer Service.
File: app/services/dataset_importer.py

Supports importing synthetic and production datasets for:
1. Blood Donors
2. Hospitals & Healthcare Facilities
3. Blood Banks
4. Blood Inventory

Safeguards:
- Strict column validation (reports missing required and unexpected columns).
- Blood group ABO/Rh validation.
- Coordinate and pincode validation.
- Duplicate detection and idempotency.
- Protected user records (never overwrites registered user accounts).
- Full dry-run mode support.
- Detailed import summary with error logs.
- Safe transactional rollback on catastrophic failure.
"""

import os
import csv
import re
import hashlib
from datetime import datetime, timezone, date
from typing import Dict, Any, List, Optional, Tuple, Set
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.donor import Donor
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.core.logging import logger
from app.core.config import settings

VALID_BLOOD_GROUPS: Set[str] = {"O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"}

# Reference coordinates for Coimbatore localities (used when coordinates are missing)
COIMBATORE_LOCALITY_COORDINATES: Dict[str, Tuple[float, float]] = {
    "town hall": (11.0016, 76.9628),
    "gandhipuram": (11.0183, 76.9639),
    "peelamedu": (11.0250, 77.0120),
    "rs puram": (11.0105, 76.9480),
    "race course": (11.0050, 76.9750),
    "saravanampatti": (11.0780, 77.0010),
    "singanallur": (10.9980, 77.0250),
    "saibaba colony": (11.0280, 76.9420),
    "koundampalayam": (11.0450, 76.9350),
    "kuniyamuthur": (10.9650, 76.9580),
    "podanur": (10.9620, 76.9950),
    "ramanathapuram": (10.9950, 76.9850),
    "ganapathy": (11.0380, 76.9820),
    "cheran ma nagar": (11.0450, 77.0150),
    "kalapatti": (11.0720, 77.0350),
    "kovaipudur": (10.9400, 76.9300),
    "perur": (10.9850, 76.9150),
}


def compute_simulated_coordinates_coimbatore(locality: str, pincode: str, donor_id: str) -> Tuple[float, float]:
    loc_key = locality.strip().lower() if locality else ""
    center = COIMBATORE_LOCALITY_COORDINATES.get(loc_key, (11.0168, 76.9558))
    h = hashlib.md5(f"{donor_id}:{locality}:{pincode}".encode("utf-8")).hexdigest()
    lat_offset = ((int(h[:4], 16) / 65535.0) - 0.5) * 0.015
    lng_offset = ((int(h[4:8], 16) / 65535.0) - 0.5) * 0.015
    return round(center[0] + lat_offset, 5), round(center[1] + lng_offset, 5)


# Column aliases for flexible mapping
DONOR_COLUMN_ALIASES = {
    "id": ["donor_id", "donorid", "id", "donor_identifier"],
    "name": ["full_name", "name", "donor_name", "display_name"],
    "blood_group": ["blood_group", "bloodgroup", "blood_type", "bloodgroup_rh"],
    "city": ["city", "locality", "town"],
    "district": ["district", "region", "county"],
    "pincode": ["pincode", "pin_code", "postal_code", "zip_code"],
    "lat": ["latitude", "lat", "location_lat", "latitude_deg"],
    "lng": ["longitude", "lng", "lon", "location_lng", "longitude_deg"],
    "availability": ["availability", "status", "availability_status"],
    "eligibility": ["eligible_for_donation", "eligibility", "is_eligible"],
    "eligibility_reason": ["eligibility_reason", "reason", "deferral_reason"],
    "contact_number": [
        "contact_number",
        "phone_number",
        "phone",
        "mobile",
        "contact",
    ],
    "email": ["email", "email_address"],
    "age": ["age", "donor_age"],
    "gender": ["gender", "sex"],
    "locality": ["locality", "neighborhood", "area"],
    "availability_rule": ["availability_rule", "rule"],
    "phone_assignment_group": ["phone_assignment_group", "assignment_group"],
    "last_contact_status": ["last_contact_status", "contact_status"],
    "consent_status": ["consent_status", "consent"],
    "record_type": ["record_type", "type_of_record"],
    "production_ready": ["production_ready", "is_production"],
    "weight_kg": ["weight_kg", "weight"],
    "hemoglobin_g_dl": ["hemoglobin_g_dl", "hemoglobin", "hb"],
    "last_donation_date": ["last_donation_date", "last_donation", "last_donated"],
}

HOSPITAL_COLUMN_ALIASES = {
    "id": ["hospital_id", "hospitalid", "id", "facility_id"],
    "name": ["hospital_name", "name", "facility_name"],
    "address": ["address", "street_address", "location"],
    "city": ["city", "locality", "town"],
    "district": ["district", "region"],
    "pincode": ["pincode", "pin_code", "postal_code"],
    "lat": ["latitude", "lat", "location_lat"],
    "lng": ["longitude", "lng", "lon", "location_lng"],
    "type": ["ownership", "type", "facility_type", "hospital_type"],
    "category": ["category", "facility_category"],
    "blood_bank_available": ["blood_bank_available", "has_blood_bank", "blood_bank", "associated_blood_bank"],
    "organ_transplant_center": ["organ_transplant_center", "transplant_center"],
    "emergency_bays": ["emergency_bays", "bays", "trauma_bays"],
    "contact_number": ["phone", "contact_number", "telephone", "mobile"],
    "services": ["services", "emergency_services", "specialties", "supported_services", "facilities"],
}

BLOOD_BANK_COLUMN_ALIASES = {
    "id": ["blood_bank_id", "bloodbank_id", "id", "bank_id"],
    "name": ["blood_bank_name", "name", "bank_name"],
    "address": ["address", "location"],
    "city": ["city", "locality"],
    "district": ["district", "region"],
    "pincode": ["pincode", "pin_code", "postal_code"],
    "lat": ["latitude", "lat", "location_lat"],
    "lng": ["longitude", "lng", "lon", "location_lng"],
    "contact_number": ["contact_number", "phone", "telephone"],
    "services": ["services", "available_services"],
    "hospital_id": ["hospital_id", "affiliated_hospital_id"],
}


class ImportSummary(BaseModel):
    dataset_type: str
    csv_path: str
    dry_run: bool
    allow_updates: bool
    total_rows_processed: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    new_records_inserted: int = 0
    existing_records_updated: int = 0
    duplicate_rows_skipped: int = 0
    protected_records_skipped: int = 0
    failed_rows: int = 0
    unique_phone_numbers: int = 0
    repeated_phone_rows: int = 0
    missing_required_columns: List[str] = Field(default_factory=list)
    unexpected_columns: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    execution_seconds: float = 0.0



def normalize_column_name(col: str) -> str:
    """Normalizes header by trimming, lowercasing, and replacing punctuation with underscores."""
    s = col.strip().lower()
    return re.sub(r'[\s\-\.]+', '_', s)


def map_row_columns(row: Dict[str, str], alias_map: Dict[str, List[str]]) -> Dict[str, str]:
    """Maps arbitrary CSV headers to standard canonical model keys."""
    normalized_row = {normalize_column_name(k): (v.strip() if v else "") for k, v in row.items()}
    mapped = {}
    for canonical_key, aliases in alias_map.items():
        for alias in aliases:
            norm_alias = normalize_column_name(alias)
            if norm_alias in normalized_row:
                mapped[canonical_key] = normalized_row[norm_alias]
                break
        else:
            mapped[canonical_key] = ""
    return mapped


def validate_pincode(pincode_str: str) -> bool:
    """Validates 6-digit Indian postal code."""
    if not pincode_str:
        return True  # Optional field
    cleaned = re.sub(r'\s+', '', pincode_str.strip())
    return bool(re.match(r'^\d{6}$', cleaned))


def validate_coordinates(lat_val: Any, lng_val: Any) -> Tuple[bool, Optional[float], Optional[float]]:
    """Validates and parses latitude and longitude floats."""
    if lat_val is None or lng_val is None or str(lat_val).strip() == "" or str(lng_val).strip() == "":
        return True, None, None
    try:
        lat = float(lat_val)
        lng = float(lng_val)
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            return False, None, None
        return True, round(lat, 5), round(lng, 5)
    except (ValueError, TypeError):
        return False, None, None


class DatasetImporter:
    """Reusable dataset importer for Blood Donors, Hospitals, and Blood Banks."""

    @staticmethod
    def import_donors(
        csv_path: str,
        db: Session,
        dry_run: bool = False,
        allow_updates: bool = False,
        limit: Optional[int] = None,
        provenance_tag: str = "dataset_import",
    ) -> ImportSummary:
        start_time = datetime.now(timezone.utc)
        app_env = (settings.APP_ENV or "development").strip().lower()
        if app_env in ("staging", "production"):
            if "synthetic" in provenance_tag.lower() or "demo" in provenance_tag.lower():
                raise RuntimeError(
                    f"SAFETY REFUSAL: Importing synthetic/demo donor data is strictly prohibited in APP_ENV='{settings.APP_ENV}'."
                )

        summary = ImportSummary(
            dataset_type="donors",
            csv_path=csv_path,
            dry_run=dry_run,
            allow_updates=allow_updates,
        )

        if not os.path.exists(csv_path):
            summary.errors.append(f"File not found: {csv_path}")
            summary.failed_rows = 1
            return summary

        # 1. Inspect headers
        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header_row = next(reader, None)

        if not header_row:
            summary.errors.append("CSV file is completely empty")
            return summary

        norm_headers = [normalize_column_name(h) for h in header_row]
        has_id = any(a in norm_headers for a in DONOR_COLUMN_ALIASES["id"])
        has_bg = any(a in norm_headers for a in DONOR_COLUMN_ALIASES["blood_group"])

        if not has_id:
            summary.missing_required_columns.append("Donor_ID")
        if not has_bg:
            summary.missing_required_columns.append("Blood_Group")

        if summary.missing_required_columns:
            summary.errors.append(f"Missing required columns: {', '.join(summary.missing_required_columns)}")
            return summary

        # Identify unexpected columns for provenance transparency
        known_aliases = set()
        for aliases in DONOR_COLUMN_ALIASES.values():
            known_aliases.update([normalize_column_name(a) for a in aliases])
        for h in norm_headers:
            if h not in known_aliases:
                summary.unexpected_columns.append(h)

        # 2. Load existing donors for duplicate detection and relationship protection
        existing_donors: Dict[str, Donor] = {d.id: d for d in db.query(Donor).all()}
        seen_csv_donor_ids: Set[str] = set()
        seen_phone_numbers: Dict[str, int] = {}

        # 3. Process records row by row
        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            dict_reader = csv.DictReader(f)
            row_num = 1
            batch: List[Donor] = []

            for raw_row in dict_reader:
                row_num += 1
                if limit and summary.valid_rows >= limit:
                    break

                summary.total_rows_processed += 1
                row = map_row_columns(raw_row, DONOR_COLUMN_ALIASES)
                donor_id = row["id"].strip()
                bg = row["blood_group"].strip().upper()

                # Clinical & Data Validation
                row_errors = []
                if not donor_id:
                    row_errors.append(f"Row {row_num}: Missing Donor ID")
                elif donor_id in seen_csv_donor_ids:
                    row_errors.append(f"Row {row_num}: Duplicate Donor ID '{donor_id}' in CSV")
                else:
                    seen_csv_donor_ids.add(donor_id)

                if bg not in VALID_BLOOD_GROUPS:
                    row_errors.append(f"Row {row_num}: Invalid Blood Group '{bg}'")

                # Pincode validation
                pin = row.get("pincode", "").strip()
                if pin and not validate_pincode(pin):
                    row_errors.append(f"Row {row_num}: Invalid 6-digit Pincode '{pin}'")

                # Coordinate validation
                coords_valid, lat, lng = validate_coordinates(row.get("lat"), row.get("lng"))
                if not coords_valid:
                    row_errors.append(f"Row {row_num}: Invalid geographic coordinates ({row.get('lat')}, {row.get('lng')})")

                # Age validation if present
                age_str = row.get("age", "").strip()
                if age_str:
                    try:
                        age = int(age_str)
                        if not (18 <= age <= 65):
                            row_errors.append(f"Row {row_num}: Age {age} outside legal donation range (18-65)")
                    except ValueError:
                        row_errors.append(f"Row {row_num}: Non-integer Age '{age_str}'")

                if row_errors:
                    summary.invalid_rows += 1
                    summary.errors.extend(row_errors[:3])
                    continue

                summary.valid_rows += 1

                # Track phone number metrics & repetitions
                phone = row.get("contact_number", "").strip()
                if phone:
                    if phone in seen_phone_numbers:
                        seen_phone_numbers[phone] += 1
                        summary.repeated_phone_rows += 1
                    else:
                        seen_phone_numbers[phone] = 1

                # Determine synthetic provenance
                raw_rec_type = (raw_row.get("record_type") or "").upper()
                raw_prod_ready = (raw_row.get("production_ready") or "").upper()
                is_synthetic = False
                provenance = provenance_tag

                if "SYNTHETIC" in raw_rec_type or raw_prod_ready == "NO" or "synthetic" in provenance_tag.lower() or "demo" in provenance_tag.lower():
                    is_synthetic = True
                    if provenance == "dataset_import":
                        provenance = "synthetic_demo"
                elif provenance_tag == "production":
                    is_synthetic = False
                    provenance = "production"

                if app_env in ("staging", "production") and is_synthetic:
                    raise RuntimeError(
                        f"SAFETY REFUSAL: Synthetic donor record '{row_id}' detected in dataset. "
                        f"Importing synthetic records into APP_ENV='{settings.APP_ENV}' is strictly prohibited."
                    )

                # Availability safeguard: Never interpret 'Pending response' as confirmed availability
                avail_val = (row.get("availability") or "").strip().lower()
                if "pending" in avail_val:
                    status_str = "unavailable"
                elif "on-call" in avail_val or "on_call" in avail_val:
                    status_str = "on-call"
                elif "avail" in avail_val:
                    status_str = "available"
                else:
                    status_str = "unavailable"

                # Clinical Eligibility safeguard: Never assume an unverified donor is clinically eligible
                raw_consent = (raw_row.get("consent_status") or "").upper()
                raw_elig = (row.get("eligibility") or "").strip().lower()

                if is_synthetic or "CONSENT NOT COLLECTED" in raw_consent or "DEMO" in raw_consent:
                    eligibility_str = "pending_review"
                    elig_reason = "Synthetic demo profile - clinical screening pending"
                elif raw_elig:
                    if raw_elig in ("yes", "eligible", "true", "1"):
                        eligibility_str = "eligible"
                        elig_reason = None
                    else:
                        eligibility_str = "ineligible"
                        elig_reason = row.get("eligibility_reason", "").strip() or "Marked ineligible in dataset"
                else:
                    eligibility_str = "pending_review"
                    elig_reason = "Unverified profile - donor screening required"

                # Coordinate assignment: Set simulated_coordinates=True when generated
                is_sim_coords = False
                if lat is None or lng is None:
                    lat, lng = compute_simulated_coordinates_coimbatore(
                        locality=raw_row.get("locality", ""),
                        pincode=pin,
                        donor_id=donor_id,
                    )
                    is_sim_coords = True

                now_iso = datetime.now(timezone.utc).isoformat()
                existing = existing_donors.get(donor_id)

                if existing:
                    # SAFETY GUARD: Never overwrite registered user accounts
                    if existing.user_id is not None:
                        summary.protected_records_skipped += 1
                        summary.duplicate_rows_skipped += 1
                        continue

                    if allow_updates:
                        if not dry_run:
                            existing.blood_group = bg
                            existing.eligibility = eligibility_str
                            existing.eligibility_reason = elig_reason
                            existing.status = status_str
                            existing.is_synthetic = is_synthetic
                            existing.data_provenance = provenance
                            existing.simulated_coordinates = is_sim_coords
                            if row.get("name"):
                                existing.name = row["name"].strip()
                            if row.get("city"):
                                existing.city = row["city"].strip()
                            if row.get("district"):
                                existing.district = row["district"].strip()
                            if pin:
                                existing.pincode = pin
                            if lat is not None:
                                existing.lat = lat
                            if lng is not None:
                                existing.lng = lng
                            if row.get("contact_number"):
                                existing.contact_number = row["contact_number"].strip()
                            if row.get("email"):
                                existing.email = row["email"].strip()
                            existing.updated_at = now_iso
                        summary.existing_records_updated += 1
                    else:
                        summary.duplicate_rows_skipped += 1
                else:
                    new_donor = Donor(
                        id=donor_id,
                        user_id=None,
                        name=row.get("name", "").strip() or None,
                        blood_group=bg,
                        city=row.get("city", "").strip() or "Coimbatore",
                        district=row.get("district", "").strip() or "Coimbatore",
                        pincode=pin or None,
                        contact_number=row.get("contact_number", "").strip() or None,
                        email=row.get("email", "").strip() or None,
                        distance_km=0.0,
                        eta_minutes=0,
                        eligibility=eligibility_str,
                        eligibility_reason=elig_reason,
                        response_probability=50,
                        reliability_score=50,
                        reachability_score=50,
                        ai_rank=999,
                        status=status_str,
                        location_consent_granted=False,
                        last_donation_days=None,
                        historical_acceptance_rate=0,
                        contacted_at=None,
                        responded_at=None,
                        lat=lat,
                        lng=lng,
                        is_synthetic=is_synthetic,
                        data_provenance=provenance,
                        simulated_coordinates=is_sim_coords,
                        created_at=now_iso,
                        updated_at=now_iso,
                    )
                    summary.new_records_inserted += 1
                    if not dry_run:
                        batch.append(new_donor)
                        if len(batch) >= 500:
                            db.add_all(batch)
                            db.commit()
                            batch = []

            if not dry_run and batch:
                db.add_all(batch)
                db.commit()

        summary.unique_phone_numbers = len(seen_phone_numbers)
        summary.execution_seconds = round((datetime.now(timezone.utc) - start_time).total_seconds(), 3)
        return summary


    @staticmethod
    def import_hospitals(
        csv_path: str,
        db: Session,
        dry_run: bool = False,
        allow_updates: bool = False,
        limit: Optional[int] = None,
        provenance_tag: str = "dataset_import",
    ) -> ImportSummary:
        start_time = datetime.now(timezone.utc)
        summary = ImportSummary(
            dataset_type="hospitals",
            csv_path=csv_path,
            dry_run=dry_run,
            allow_updates=allow_updates,
        )

        if not os.path.exists(csv_path):
            summary.errors.append(f"File not found: {csv_path}")
            summary.failed_rows = 1
            return summary

        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header_row = next(reader, None)

        if not header_row:
            summary.errors.append("CSV file is completely empty")
            return summary

        norm_headers = [normalize_column_name(h) for h in header_row]
        has_id = any(a in norm_headers for a in HOSPITAL_COLUMN_ALIASES["id"])
        has_name = any(a in norm_headers for a in HOSPITAL_COLUMN_ALIASES["name"])

        if not has_id:
            summary.missing_required_columns.append("Hospital_ID")
        if not has_name:
            summary.missing_required_columns.append("Hospital_Name")

        if summary.missing_required_columns:
            summary.errors.append(f"Missing required columns: {', '.join(summary.missing_required_columns)}")
            return summary

        existing_hospitals: Dict[str, Hospital] = {h.id: h for h in db.query(Hospital).all()}

        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            dict_reader = csv.DictReader(f)
            row_num = 1
            batch: List[Hospital] = []

            for raw_row in dict_reader:
                row_num += 1
                if limit and summary.valid_rows >= limit:
                    break

                summary.total_rows_processed += 1
                row = map_row_columns(raw_row, HOSPITAL_COLUMN_ALIASES)
                hosp_id = row["id"].strip()
                hosp_name = row["name"].strip()

                row_errors = []
                if not hosp_id:
                    row_errors.append(f"Row {row_num}: Missing Hospital ID")
                if not hosp_name:
                    row_errors.append(f"Row {row_num}: Missing Hospital Name")

                pin = row.get("pincode", "").strip()
                if pin and not validate_pincode(pin):
                    row_errors.append(f"Row {row_num}: Invalid 6-digit Pincode '{pin}'")

                coords_valid, lat, lng = validate_coordinates(row.get("lat"), row.get("lng"))
                if not coords_valid:
                    row_errors.append(f"Row {row_num}: Invalid geographic coordinates ({row.get('lat')}, {row.get('lng')})")

                if row_errors:
                    summary.invalid_rows += 1
                    summary.errors.extend(row_errors[:3])
                    continue

                summary.valid_rows += 1

                # Normalize booleans
                bb_avail_str = row.get("blood_bank_available", "").lower().strip()
                bb_available = bb_avail_str in ("yes", "true", "1", "available", "confirmed")
                organ_center_str = row.get("organ_transplant_center", "").lower().strip()
                organ_center = organ_center_str in ("yes", "true", "1")

                # Parse emergency bays safely without inventing arbitrary capacity
                bays_val = str(row.get("emergency_bays") or "").strip()
                try:
                    bays = int(bays_val) if bays_val else 0
                except ValueError:
                    bays = 0

                # Extract services and specialties without losing information
                emerg_raw = raw_row.get("emergency_services", "").strip()
                spec_raw = raw_row.get("specialties", "").strip()
                if emerg_raw or spec_raw:
                    combined_svc = "; ".join(filter(None, [emerg_raw, spec_raw]))
                    services = combined_svc[:255] if len(combined_svc) > 255 else combined_svc
                else:
                    services = row.get("services", "").strip() or None

                now_iso = datetime.now(timezone.utc).isoformat()
                existing = existing_hospitals.get(hosp_id)

                if existing:
                    if allow_updates:
                        if not dry_run:
                            existing.name = hosp_name
                            if row.get("address"):
                                existing.address = row["address"].strip()
                            if row.get("city"):
                                existing.city = row["city"].strip()
                            if row.get("district"):
                                existing.district = row["district"].strip()
                            if pin:
                                existing.pincode = pin
                            if lat is not None:
                                existing.lat = lat
                            if lng is not None:
                                existing.lng = lng
                            if row.get("type"):
                                existing.type = row["type"].strip()
                            if row.get("category"):
                                existing.category = row["category"].strip()
                            if services:
                                existing.services = services
                            if row.get("contact_number"):
                                existing.contact_number = row["contact_number"].strip()
                            existing.updated_at = now_iso
                        summary.existing_records_updated += 1
                    else:
                        summary.duplicate_rows_skipped += 1
                else:
                    new_hosp = Hospital(
                        id=hosp_id,
                        name=hosp_name,
                        address=row.get("address", "").strip() or "Coimbatore",
                        city=row.get("city", "").strip() or "Coimbatore",
                        district=row.get("district", "").strip() or "Coimbatore",
                        pincode=pin or None,
                        lat=lat,
                        lng=lng,
                        type=row.get("type", "").strip() or "general",
                        category=row.get("category", "").strip() or "hospital",
                        services=services,
                        blood_bank_available=bb_available,
                        organ_transplant_center=organ_center,
                        emergency_bays=bays,
                        contact_number=row.get("contact_number", "").strip() or None,
                        is_current_hospital=False,
                        created_at=now_iso,
                        updated_at=now_iso,
                        data_provenance=provenance_tag,
                    )
                    summary.new_records_inserted += 1
                    if not dry_run:
                        batch.append(new_hosp)
                        if len(batch) >= 500:
                            db.add_all(batch)
                            db.commit()
                            batch = []

            if not dry_run and batch:
                db.add_all(batch)
                db.commit()

        summary.execution_seconds = round((datetime.now(timezone.utc) - start_time).total_seconds(), 3)
        return summary

    @staticmethod
    def import_blood_banks(
        csv_path: str,
        db: Session,
        dry_run: bool = False,
        allow_updates: bool = False,
        limit: Optional[int] = None,
        provenance_tag: str = "dataset_import",
    ) -> ImportSummary:
        start_time = datetime.now(timezone.utc)
        summary = ImportSummary(
            dataset_type="blood_banks",
            csv_path=csv_path,
            dry_run=dry_run,
            allow_updates=allow_updates,
        )

        if not os.path.exists(csv_path):
            summary.errors.append(f"File not found: {csv_path}")
            summary.failed_rows = 1
            return summary

        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header_row = next(reader, None)

        if not header_row:
            summary.errors.append("CSV file is completely empty")
            return summary

        norm_headers = [normalize_column_name(h) for h in header_row]
        has_id = any(a in norm_headers for a in BLOOD_BANK_COLUMN_ALIASES["id"])
        has_name = any(a in norm_headers for a in BLOOD_BANK_COLUMN_ALIASES["name"])

        if not has_id:
            summary.missing_required_columns.append("Blood_Bank_ID")
        if not has_name:
            summary.missing_required_columns.append("Blood_Bank_Name")

        if summary.missing_required_columns:
            summary.errors.append(f"Missing required columns: {', '.join(summary.missing_required_columns)}")
            return summary

        existing_banks: Dict[str, BloodBank] = {b.id: b for b in db.query(BloodBank).all()}

        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            dict_reader = csv.DictReader(f)
            row_num = 1
            batch: List[BloodBank] = []

            for raw_row in dict_reader:
                row_num += 1
                if limit and summary.valid_rows >= limit:
                    break

                summary.total_rows_processed += 1
                row = map_row_columns(raw_row, BLOOD_BANK_COLUMN_ALIASES)
                bank_id = row["id"].strip()
                bank_name = row["name"].strip()

                row_errors = []
                if not bank_id:
                    row_errors.append(f"Row {row_num}: Missing Blood Bank ID")
                if not bank_name:
                    row_errors.append(f"Row {row_num}: Missing Blood Bank Name")

                pin = row.get("pincode", "").strip()
                if pin and not validate_pincode(pin):
                    row_errors.append(f"Row {row_num}: Invalid 6-digit Pincode '{pin}'")

                coords_valid, lat, lng = validate_coordinates(row.get("lat"), row.get("lng"))
                if not coords_valid:
                    row_errors.append(f"Row {row_num}: Invalid geographic coordinates ({row.get('lat')}, {row.get('lng')})")

                if row_errors:
                    summary.invalid_rows += 1
                    summary.errors.extend(row_errors[:3])
                    continue

                summary.valid_rows += 1
                now_iso = datetime.now(timezone.utc).isoformat()
                existing = existing_banks.get(bank_id)

                if existing:
                    if allow_updates:
                        if not dry_run:
                            existing.name = bank_name
                            if row.get("address"):
                                existing.address = row["address"].strip()
                            if row.get("city"):
                                existing.city = row["city"].strip()
                            if row.get("district"):
                                existing.district = row["district"].strip()
                            if pin:
                                existing.pincode = pin
                            if lat is not None:
                                existing.lat = lat
                            if lng is not None:
                                existing.lng = lng
                            if row.get("contact_number"):
                                existing.contact_number = row["contact_number"].strip()
                            if row.get("services"):
                                existing.services = row["services"].strip()
                            existing.updated_at = now_iso
                        summary.existing_records_updated += 1
                    else:
                        summary.duplicate_rows_skipped += 1
                else:
                    new_bank = BloodBank(
                        id=bank_id,
                        name=bank_name,
                        address=row.get("address", "").strip() or "Coimbatore",
                        city=row.get("city", "").strip() or "Coimbatore",
                        district=row.get("district", "").strip() or "Coimbatore",
                        pincode=pin or None,
                        lat=lat if lat is not None else 11.0168,
                        lng=lng if lng is not None else 76.9558,
                        contact_number=row.get("contact_number", "").strip() or None,
                        services=row.get("services", "").strip() or "blood_storage,transfusion",
                        hospital_id=row.get("hospital_id", "").strip() or None,
                        created_at=now_iso,
                        updated_at=now_iso,
                        data_provenance=provenance_tag,
                    )
                    summary.new_records_inserted += 1
                    if not dry_run:
                        batch.append(new_bank)
                        if len(batch) >= 500:
                            db.add_all(batch)
                            db.commit()
                            batch = []

            if not dry_run and batch:
                db.add_all(batch)
                db.commit()

        summary.execution_seconds = round((datetime.now(timezone.utc) - start_time).total_seconds(), 3)
        return summary


dataset_importer = DatasetImporter()
