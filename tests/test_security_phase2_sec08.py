"""
Tests for SEC-08: Production Database and Synthetic-Data Safeguards
Verifies:
1. Production configuration rejects AUTO_SEED_DATA=True.
2. Production startup/init_db refuses demo seeding.
3. DatasetImporter rejects synthetic or demo donor dataset imports in production.
4. DatasetImporter permits genuine production records in production.
5. Production matching strictly excludes synthetic records from dispatch.
"""
import pytest
import csv
from pydantic import ValidationError
from app.core.config import Settings, settings
from app.db.init_db import init_db
from app.services.dataset_importer import DatasetImporter
from app.services.donor_service import DonorService
from app.models.donor import Donor
from app.models.emergency import Emergency


def test_sec08_production_auto_seed_data_rejected():
    """Production settings validation raises ValueError if AUTO_SEED_DATA is set to True."""
    with pytest.raises((ValueError, ValidationError)) as exc_info:
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="e4d909c290d0fb1ca068ffaddf22cbd0e4d909c290d0fb1ca068ffaddf22cbd0",
            DATABASE_URL="postgresql+psycopg://prod:pass@localhost:5432/lifelink_prod",
            CORS_ORIGINS=["https://app.lifelink.org"],
            AUTO_SEED_DATA=True,
        )
    assert "AUTO_SEED_DATA cannot be True in APP_ENV='production'" in str(exc_info.value)


def test_sec08_production_init_db_refuses_seeding(db, monkeypatch):
    """Calling init_db with APP_ENV=production exits immediately without seeding demo data."""
    monkeypatch.setattr(settings, "APP_ENV", "production")
    # Record initial counts
    donor_count_before = db.query(Donor).count()

    init_db(db)

    donor_count_after = db.query(Donor).count()
    assert donor_count_before == donor_count_after


def test_sec08_production_rejects_synthetic_dataset_import(db, tmp_path, monkeypatch):
    """DatasetImporter refuses to import synthetic demo data into production/staging environments."""
    monkeypatch.setattr(settings, "APP_ENV", "production")

    csv_file = tmp_path / "synthetic_donors.csv"
    headers = ["donor_id", "full_name", "blood_group", "city", "record_type", "production_ready"]
    rows = [
        ["DEMO-001", "Synthetic Test Donor", "O+", "Coimbatore", "SYNTHETIC DEMO RECORD", "NO"]
    ]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    with pytest.raises(RuntimeError) as exc_info:
        DatasetImporter.import_donors(str(csv_file), db=db, dry_run=False, provenance_tag="synthetic_demo")
    assert "SAFETY REFUSAL" in str(exc_info.value)
    assert "synthetic" in str(exc_info.value).lower()


def test_sec08_production_allows_real_donor_import(db, tmp_path, monkeypatch):
    """DatasetImporter permits real, verified production donor records in production environment."""
    monkeypatch.setattr(settings, "APP_ENV", "production")

    csv_file = tmp_path / "production_donors.csv"
    headers = ["donor_id", "full_name", "blood_group", "city", "phone", "eligibility", "record_type", "production_ready"]
    rows = [
        ["REAL-PROD-001", "Genuine Verified Donor", "A+", "Coimbatore", "9876543210", "eligible", "PRODUCTION", "YES"]
    ]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    summary = DatasetImporter.import_donors(str(csv_file), db=db, dry_run=False, provenance_tag="production")
    assert summary.new_records_inserted == 1

    d = db.query(Donor).filter(Donor.id == "REAL-PROD-001").first()
    assert d is not None
    assert d.is_synthetic is False
    assert d.data_provenance == "production"


def test_sec08_matching_excludes_synthetic_donors_from_dispatch(db):
    """Real emergency matching algorithms strictly exclude synthetic profiles from production candidate pools."""
    synth_donor = Donor(
        id="D-SYNTH-MATCH-TEST",
        blood_group="O+",
        eligibility="eligible",
        status="available",
        lat=11.0183,
        lng=76.9639,
        is_synthetic=True,
        data_provenance="synthetic_demo",
    )
    db.merge(synth_donor)
    db.commit()

    # Query ranked donors for emergency BL-102 (production emergency)
    resp = DonorService.get_ranked_donors(
        db=db,
        emergency_id="BL-102",
        demo_mode=False,
    )
    candidate_ids = [c.id for c in resp.donors]
    assert "D-SYNTH-MATCH-TEST" not in candidate_ids
