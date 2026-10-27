"""
Coimbatore Hospital Dataset Integration and API Verification Suite.

Tests hospital dataset ingestion, non-fabrication safeguards,
and hospital API endpoints with query filtering.
"""
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import get_db
from app.models.hospital import Hospital


@pytest.fixture
def client():
    return TestClient(app)


def test_starter_hospital_dataset_file_and_csv_integrity():
    """Verify that both the starter XLSX and converted CSV exist and match row counts."""
    xlsx_path = "data/LifeLink_Coimbatore_Hospital_Dataset_Starter.xlsx"
    csv_path = "data/LifeLink_Coimbatore_Hospital_Dataset_Starter.csv"
    assert os.path.exists(xlsx_path), f"Starter XLSX file missing at {xlsx_path}"
    assert os.path.exists(csv_path), f"Starter CSV file missing at {csv_path}"

    with open(csv_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    # 1 header + 15 hospital records
    assert len(lines) == 16, f"Expected 16 lines (header + 15 data rows), got {len(lines)}"


def test_hospital_database_integrity_and_provenance():
    """Verify that all 15 starter hospitals exist in DB and preserve baseline records."""
    db_gen = get_db()
    db: Session = next(db_gen)
    try:
        all_hospitals = db.query(Hospital).all()
        # 4 baseline + 15 imported
        assert len(all_hospitals) >= 19

        # Verify baseline hospitals are intact
        baseline_ids = {"city-hospital-001", "apollo-001", "manipal-001", "fortis-001"}
        present_baseline = {h.id for h in all_hospitals if h.id in baseline_ids}
        assert present_baseline == baseline_ids, "Baseline hospital records were modified or missing"

        # Verify imported hospitals have dataset_import provenance
        imported_hospitals = [h for h in all_hospitals if h.data_provenance == "dataset_import"]
        assert len(imported_hospitals) == 15

        # Verify non-fabrication of coordinates and blood banks for unverified starter rows
        gov_001 = db.query(Hospital).filter(Hospital.id == "CBE-GOV-001").first()
        assert gov_001 is not None
        assert gov_001.lat is None, "Coordinates must not be fabricated when unverified in source"
        assert gov_001.lng is None, "Coordinates must not be fabricated when unverified in source"
        assert gov_001.blood_bank_available is False, "Blood bank availability must not be fabricated"
        assert gov_001.type == "Government"
        assert gov_001.city == "Coimbatore"
        assert gov_001.pincode == "641018"
    finally:
        db.close()


def test_api_list_hospitals_and_filters(client: TestClient):
    """Test /api/v1/hospitals listing and filtering capabilities."""
    # List all
    res_all = client.get("/api/v1/hospitals")
    assert res_all.status_code == 200
    hospitals = res_all.json()
    assert len(hospitals) >= 19

    # Filter city=Coimbatore
    res_cbe = client.get("/api/v1/hospitals?city=Coimbatore")
    assert res_cbe.status_code == 200
    cbe_hospitals = res_cbe.json()
    assert len(cbe_hospitals) >= 12
    for h in cbe_hospitals:
        assert "coimbatore" in h["city"].lower()

    # Filter district=Coimbatore
    res_dist = client.get("/api/v1/hospitals?district=Coimbatore")
    assert res_dist.status_code == 200
    assert len(res_dist.json()) >= 15

    # Filter type=Government (case-insensitive)
    res_gov = client.get("/api/v1/hospitals?type=Government")
    assert res_gov.status_code == 200
    gov_hospitals = res_gov.json()
    assert len(gov_hospitals) == 5
    for h in gov_hospitals:
        assert h["type"] == "Government"

    # Filter type=Private
    res_pri = client.get("/api/v1/hospitals?type=Private")
    assert res_pri.status_code == 200
    pri_hospitals = res_pri.json()
    assert len(pri_hospitals) >= 10


def test_api_get_hospital_by_id(client: TestClient):
    """Test /api/v1/hospitals/{hospital_id} for imported and baseline records."""
    # Imported hospital without coordinates
    res_cbe = client.get("/api/v1/hospitals/CBE-GOV-001")
    assert res_cbe.status_code == 200
    data_cbe = res_cbe.json()
    assert data_cbe["id"] == "CBE-GOV-001"
    assert data_cbe["name"] == "Government Coimbatore Medical College Hospital"
    assert data_cbe["coordinates"] is None
    assert data_cbe["contactNumber"] == "0422-2301393"

    # Baseline hospital with coordinates
    res_base = client.get("/api/v1/hospitals/city-hospital-001")
    assert res_base.status_code == 200
    data_base = res_base.json()
    assert data_base["id"] == "city-hospital-001"
    assert data_base["coordinates"] is not None
    assert data_base["coordinates"]["lat"] == 12.9716

    # Non-existent hospital returns 404
    res_404 = client.get("/api/v1/hospitals/non-existent-999")
    assert res_404.status_code == 404


def test_api_get_hospital_inventory(client: TestClient):
    """Test /api/v1/hospitals/{hospital_id}/inventory response."""
    res_inv = client.get("/api/v1/hospitals/CBE-GOV-001/inventory")
    assert res_inv.status_code == 200
    data_inv = res_inv.json()
    assert data_inv["hospitalId"] == "CBE-GOV-001"
    assert "bloodInventory" in data_inv
    assert "emergencyBaysTotal" in data_inv
    assert data_inv["emergencyBaysTotal"] == 0
