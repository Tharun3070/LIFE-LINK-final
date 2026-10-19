"""
Tests for LifeLink Synthetic Donor Dataset Importer
File: backend/tests/test_donor_importer.py

Validates:
1. Hard validation (invalid blood group, age, weight, hemoglobin).
2. Dry-run option (database untouched, report accurately returned).
3. Limit option (restricts number of imported records).
4. Idempotency (repeated runs do not create duplicate donors or corrupt state).
5. Protected donor records and user relationships (never overwrites user-linked donors).
6. Synthetic provenance tracking (is_synthetic=True, data_provenance='synthetic_registry').
7. Safety guard: Contact attempts on synthetic donors are strictly blocked (HTTP 403).
8. Missing historical data representation (historical_acceptance_rate=0).
"""

import os
import tempfile
import pytest
from app.models.donor import Donor
from app.models.user import User
from app.models.consent import Consent
from app.services.donor_service import DonorService
from app.schemas.auth import UserProfileSchema
from scripts.import_donors_csv import import_donors, validate_row, parse_last_donation_days


SAMPLE_CSV_CONTENT = """Donor_ID,Full_Name,Gender,Age,Blood_Group,Contact_Number,Email,City,State,Country,Last_Donation_Date,Total_Donations,Eligible_for_Donation,Medical_Condition,Weight_kg,Hemoglobin_g_dL,Donation_Center,Registration_Date,Tattooed,Tattoo_Date,Recently_Donated,Taking_Medicine,Medicine_Type,Fever,Infection,Recent_Surgery,Availability,Eligibility_Reason
LLD-TEST001,John Doe,Male,28,O+,+919876543210,john.doe1@example.com,Bengaluru,Karnataka,India,2026-01-15,3,Yes,,70.5,14.5,City Hospital,2024-01-01,No,,No,No,,No,No,No,Available,Eligible for prototype matching
LLD-TEST002,Jane Smith,Female,32,A-,+919876543211,jane.smith2@example.com,Bengaluru,Karnataka,India,,0,No,,50.0,11.2,City Hospital,2024-02-01,No,,No,No,,No,No,No,Unavailable,Hemoglobin below prototype threshold
LLD-TEST003,Bob Wilson,Male,45,B+,+919876543212,bob.w3@example.com,Mumbai,Maharashtra,India,2025-06-20,5,Yes,,80.0,15.1,Apollo Center,2023-05-15,No,,No,No,,No,No,No,On-call,Eligible for prototype matching
"""

INVALID_CSV_CONTENT = """Donor_ID,Full_Name,Gender,Age,Blood_Group,Contact_Number,Email,City,State,Country,Last_Donation_Date,Total_Donations,Eligible_for_Donation,Medical_Condition,Weight_kg,Hemoglobin_g_dL,Donation_Center,Registration_Date,Tattooed,Tattoo_Date,Recently_Donated,Taking_Medicine,Medicine_Type,Fever,Infection,Recent_Surgery,Availability,Eligibility_Reason
LLD-INV01,Bad Blood,Male,30,INVALID_GROUP,+919876543213,bad.blood@example.com,Bengaluru,Karnataka,India,,0,Yes,,65.0,14.0,Center,2024-01-01,No,,No,No,,No,No,No,Available,Eligible
LLD-INV02,Underage,Male,16,O+,+919876543214,underage@example.com,Bengaluru,Karnataka,India,,0,Yes,,60.0,14.0,Center,2024-01-01,No,,No,No,,No,No,No,Available,Eligible
LLD-INV03,Underweight,Female,25,O+,+919876543215,underweight@example.com,Bengaluru,Karnataka,India,,0,Yes,,40.0,13.5,Center,2024-01-01,No,,No,No,,No,No,No,Available,Eligible
"""


@pytest.fixture
def sample_csv_file():
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv", encoding="utf-8") as f:
        f.write(SAMPLE_CSV_CONTENT)
        path = f.name
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def invalid_csv_file():
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv", encoding="utf-8") as f:
        f.write(INVALID_CSV_CONTENT)
        path = f.name
    yield path
    if os.path.exists(path):
        os.remove(path)


# ---------------------------------------------------------------------------
# 1. Row Validation Tests
# ---------------------------------------------------------------------------

def test_validate_row_valid_and_invalid():
    valid_row = {
        "Donor_ID": "LLD-001", "Blood_Group": "O+", "Eligible_for_Donation": "Yes",
        "Availability": "Available", "Age": "25", "Weight_kg": "65.0", "Hemoglobin_g_dL": "14.2"
    }
    is_valid, errors = validate_row(valid_row, 1)
    assert is_valid is True
    assert len(errors) == 0

    # Invalid blood group
    invalid_bg_row = {**valid_row, "Blood_Group": "XYZ"}
    is_valid, errors = validate_row(invalid_bg_row, 2)
    assert is_valid is False
    assert any("Invalid Blood_Group" in e for e in errors)

    # Underage donor
    underage_row = {**valid_row, "Age": "17"}
    is_valid, errors = validate_row(underage_row, 3)
    assert is_valid is False
    assert any("Age 17 outside legal" in e for e in errors)

    # Underweight donor
    underweight_row = {**valid_row, "Weight_kg": "42.0"}
    is_valid, errors = validate_row(underweight_row, 4)
    assert is_valid is False
    assert any("below minimum 45 kg" in e for e in errors)


# ---------------------------------------------------------------------------
# 2. Dry Run & Limit Tests
# ---------------------------------------------------------------------------

def test_importer_dry_run_leaves_database_untouched(db, sample_csv_file):
    initial_count = db.query(Donor).count()

    report = import_donors(csv_path=sample_csv_file, dry_run=True, session=db)

    assert report["status"] == "success"
    assert report["dry_run"] is True
    assert report["valid_records"] == 3
    assert report["inserted_count"] == 3

    # Database state must be unchanged
    final_count = db.query(Donor).count()
    assert final_count == initial_count
    assert db.query(Donor).filter(Donor.id == "LLD-TEST001").first() is None


def test_importer_limit_option(db, sample_csv_file):
    report = import_donors(csv_path=sample_csv_file, dry_run=False, limit=2, session=db)

    assert report["status"] == "success"
    assert report["valid_records"] == 2
    assert report["inserted_count"] == 2

    # Exactly 2 donors imported
    assert db.query(Donor).filter(Donor.id == "LLD-TEST001").first() is not None
    assert db.query(Donor).filter(Donor.id == "LLD-TEST002").first() is not None
    assert db.query(Donor).filter(Donor.id == "LLD-TEST003").first() is None


def test_importer_skips_invalid_records(db, invalid_csv_file):
    report = import_donors(csv_path=invalid_csv_file, dry_run=False, session=db)

    assert report["status"] == "success"
    assert report["invalid_records"] == 3
    assert report["inserted_count"] == 0
    assert len(report["validation_errors"]) >= 3


# ---------------------------------------------------------------------------
# 3. Duplicate Detection & Idempotency
# ---------------------------------------------------------------------------

def test_importer_idempotency(db, sample_csv_file):
    """Running import multiple times must not produce duplicate donors or errors."""
    # First run: inserts 3
    report1 = import_donors(csv_path=sample_csv_file, dry_run=False, session=db)
    assert report1["inserted_count"] == 3
    count_after_first = db.query(Donor).count()

    # Second run: updates 3, inserts 0
    report2 = import_donors(csv_path=sample_csv_file, dry_run=False, session=db)
    assert report2["inserted_count"] == 0
    assert report2["updated_count"] == 3

    # Donor count must remain strictly identical
    count_after_second = db.query(Donor).count()
    assert count_after_second == count_after_first


# ---------------------------------------------------------------------------
# 4. Protection of Existing Records & Database Relationships
# ---------------------------------------------------------------------------

def test_importer_protects_existing_user_linked_donors(db):
    """
    If a CSV record collision matches an existing registered user-linked donor,
    the importer must protect the existing donor and user relationship without overwriting.
    """
    # D-101 is seeded with user_id="usr-dnr-005"
    donor_101 = db.query(Donor).filter(Donor.id == "D-101").first()
    assert donor_101 is not None
    original_user_id = donor_101.user_id
    assert original_user_id == "usr-dnr-005"

    # Create CSV containing D-101
    collision_csv = """Donor_ID,Full_Name,Gender,Age,Blood_Group,Contact_Number,Email,City,State,Country,Last_Donation_Date,Total_Donations,Eligible_for_Donation,Medical_Condition,Weight_kg,Hemoglobin_g_dL,Donation_Center,Registration_Date,Tattooed,Tattoo_Date,Recently_Donated,Taking_Medicine,Medicine_Type,Fever,Infection,Recent_Surgery,Availability,Eligibility_Reason
D-101,Malicious Overwrite,Male,25,A+,+919876543299,hacked@example.com,Bengaluru,Karnataka,India,,0,Yes,,70.0,14.0,Center,2024-01-01,No,,No,No,,No,No,No,Available,Eligible
"""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv", encoding="utf-8") as f:
        f.write(collision_csv)
        path = f.name

    try:
        report = import_donors(csv_path=path, dry_run=False, session=db)
        assert report["protected_count"] == 1
        assert report["updated_count"] == 0
        assert report["inserted_count"] == 0

        # Verify donor_101 was not overwritten
        reloaded = db.query(Donor).filter(Donor.id == "D-101").first()
        assert reloaded.user_id == original_user_id
        assert reloaded.blood_group == "O-"  # Preserved original blood group
    finally:
        if os.path.exists(path):
            os.remove(path)


# ---------------------------------------------------------------------------
# 5. Provenance & Safety Guards (Never Alert Synthetic Donors)
# ---------------------------------------------------------------------------

def test_synthetic_provenance_and_safety_guard_blocks_contact(db, sample_csv_file):
    """
    Imported donors must be marked is_synthetic=True and data_provenance='synthetic_registry'.
    Calling DonorService.contact_donor() on a synthetic profile must raise HTTP 403 Forbidden.
    """
    import_donors(csv_path=sample_csv_file, dry_run=False, session=db)

    donor = db.query(Donor).filter(Donor.id == "LLD-TEST001").first()
    assert donor is not None
    assert donor.is_synthetic is True
    assert donor.data_provenance == "synthetic_registry"
    assert donor.user_id is None
    # Unobserved history explicitly represented as 0
    assert donor.historical_acceptance_rate == 0

    doctor_user = UserProfileSchema(
        id="usr-doc-001",
        name="Dr. Arjun Rao",
        email="doctor@lifelink.demo",
        role="doctor",
    )

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        DonorService.contact_donor(db, donor_id="LLD-TEST001", emergency_id="BL-102", current_user=doctor_user)

    assert exc_info.value.status_code == 403
    assert "synthetic benchmark profile" in exc_info.value.detail.lower()


def test_parse_last_donation_days_date_formats():
    """Verifies that parse_last_donation_days handles both ISO (%Y-%m-%d) and DD-MM-YYYY formats."""
    from datetime import date
    ref = date(2026, 10, 10)

    # ISO format (%Y-%m-%d)
    days_iso = parse_last_donation_days("2026-01-15", ref_date=ref)
    assert days_iso is not None
    assert days_iso == (ref - date(2026, 1, 15)).days

    # DD-MM-YYYY format from 30K dataset (e.g., 30-11-2023)
    days_dmy = parse_last_donation_days("30-11-2023", ref_date=ref)
    assert days_dmy is not None
    assert days_dmy == (ref - date(2023, 11, 30)).days

    # Empty / whitespace / None returns None
    assert parse_last_donation_days("") is None
    assert parse_last_donation_days("   ") is None
    assert parse_last_donation_days(None) is None
    assert parse_last_donation_days("invalid-date") is None


def test_contact_donor_pending_review_blocked(db):
    """A donor with eligibility='pending_review' must be blocked from contact dispatch."""
    donor = Donor(
        id="D-REVIEW-01",
        blood_group="O-",
        eligibility="pending_review",
        eligibility_reason="Needs blood test",
        status="available",
        user_id="usr-dnr-005",  # Has consent
        is_synthetic=False,
        data_provenance="production",
    )
    db.add(donor)
    db.commit()

    doctor_user = UserProfileSchema(
        id="usr-doc-001",
        name="Dr. Arjun Rao",
        email="doctor@lifelink.demo",
        role="doctor",
    )

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        DonorService.contact_donor(db, donor_id="D-REVIEW-01", emergency_id="BL-102", current_user=doctor_user)

    assert exc_info.value.status_code == 400
    assert "status is inappropriate for contact" in exc_info.value.detail.lower()
