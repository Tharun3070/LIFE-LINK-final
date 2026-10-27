import pytest
import csv
from app.core.config import settings
from app.models.donor import Donor
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.blood_inventory import BloodInventory
from app.services.dataset_importer import DatasetImporter


@pytest.fixture(autouse=True)
def mock_external_services(monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "")
    monkeypatch.setattr(settings, "GOOGLE_MAPS_API_KEY", "")


def test_import_donors_success(db, tmp_path):
    csv_file = tmp_path / "valid_donors.csv"
    headers = ["donor_id", "full_name", "blood_group", "city", "district", "pincode", "latitude", "longitude", "phone", "email"]
    rows = [
        ["D-IMP-001", "Karthik Raja", "O+", "Coimbatore", "Coimbatore", "641018", "11.0183", "76.9639", "9876543210", "karthik@example.com"],
        ["D-IMP-002", "Priya Sundaram", "A-", "Coimbatore", "Coimbatore", "641004", "11.0250", "76.9550", "9876543211", "priya@example.com"],
    ]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    summary = DatasetImporter.import_donors(str(csv_file), db=db, dry_run=False, allow_updates=False)

    assert summary.valid_rows == 2
    assert summary.new_records_inserted == 2
    assert summary.failed_rows == 0
    assert len(summary.errors) == 0

    donor = db.query(Donor).filter(Donor.id == "D-IMP-001").first()
    assert donor is not None
    assert donor.name == "Karthik Raja"
    assert donor.blood_group == "O+"
    assert donor.city == "Coimbatore"
    assert donor.pincode == "641018"
    assert donor.contact_number == "9876543210"


def test_import_donors_dry_run(db, tmp_path):
    csv_file = tmp_path / "dry_run_donors.csv"
    headers = ["donor_id", "full_name", "blood_group", "city", "pincode"]
    rows = [["D-DRY-001", "Senthil Kumar", "B+", "Coimbatore", "641001"]]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    summary = DatasetImporter.import_donors(str(csv_file), db=db, dry_run=True)

    assert summary.valid_rows == 1
    assert summary.new_records_inserted == 1
    assert summary.dry_run is True

    # Database must remain untouched in dry run
    donor = db.query(Donor).filter(Donor.id == "D-DRY-001").first()
    assert donor is None


def test_import_donors_missing_required_column(db, tmp_path):
    csv_file = tmp_path / "missing_col.csv"
    headers = ["donor_id", "full_name", "city"]
    rows = [["D-001", "Test Donor", "Coimbatore"]]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    summary = DatasetImporter.import_donors(str(csv_file), db=db)
    assert "Blood_Group" in summary.missing_required_columns
    assert len(summary.errors) > 0
    assert summary.valid_rows == 0


def test_import_donors_invalid_data_safeguards(db, tmp_path):
    csv_file = tmp_path / "invalid_rows.csv"
    headers = ["donor_id", "full_name", "blood_group", "latitude", "longitude", "pincode"]
    rows = [
        ["D-INV-001", "Invalid Blood", "X+", "11.0", "76.9", "641001"],  # Bad blood group
        ["D-INV-002", "Invalid Lat", "O+", "195.0", "76.9", "641001"],  # Bad latitude
        ["D-INV-003", "Invalid Pin", "A+", "11.0", "76.9", "123"],       # Bad pincode (not 6 digits)
    ]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    summary = DatasetImporter.import_donors(str(csv_file), db=db, dry_run=False)
    assert summary.invalid_rows == 3
    assert summary.new_records_inserted == 0
    assert len(summary.errors) >= 3


def test_import_donors_duplicate_and_update(db, tmp_path):
    csv_file = tmp_path / "dup_donors.csv"
    headers = ["donor_id", "full_name", "blood_group", "city"]
    rows = [["D-DUP-001", "Original Name", "AB+", "Coimbatore"]]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    # First import
    s1 = DatasetImporter.import_donors(str(csv_file), db=db, dry_run=False, allow_updates=False)
    assert s1.new_records_inserted == 1

    # Second import without allow_updates -> skipped
    s2 = DatasetImporter.import_donors(str(csv_file), db=db, dry_run=False, allow_updates=False)
    assert s2.duplicate_rows_skipped == 1
    assert s2.new_records_inserted == 0

    # Third import with updated name and allow_updates=True
    rows_updated = [["D-DUP-001", "Updated Name", "AB+", "Coimbatore"]]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows_updated)

    s3 = DatasetImporter.import_donors(str(csv_file), db=db, dry_run=False, allow_updates=True)
    assert s3.existing_records_updated == 1

    donor = db.query(Donor).filter(Donor.id == "D-DUP-001").first()
    assert donor.name == "Updated Name"


def test_import_donors_preserves_registered_user_accounts(db, tmp_path):
    # Create protected donor tied to registered user account
    protected_donor = Donor(
        id="D-USER-PROTECTED",
        user_id="user-account-12345",
        blood_group="O+",
        city="Coimbatore",
        lat=11.0,
        lng=76.9,
        status="available",
    )
    db.add(protected_donor)
    db.commit()


    csv_file = tmp_path / "protected_donor.csv"
    headers = ["donor_id", "full_name", "blood_group", "city"]
    rows = [["D-USER-PROTECTED", "Attempted Overwrite", "O+", "Chennai"]]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    summary = DatasetImporter.import_donors(str(csv_file), db=db, dry_run=False, allow_updates=True)
    assert summary.protected_records_skipped == 1
    assert summary.existing_records_updated == 0

    # Verify donor still has user_id and city wasn't overwritten
    d = db.query(Donor).filter(Donor.id == "D-USER-PROTECTED").first()
    assert d.user_id == "user-account-12345"
    assert d.city == "Coimbatore"


def test_import_hospitals_success(db, tmp_path):
    csv_file = tmp_path / "hospitals.csv"
    headers = ["hospital_id", "facility_name", "address", "city", "district", "pincode", "latitude", "longitude", "category", "trauma_bays", "services"]
    rows = [
        ["H-IMP-001", "Coimbatore Central Medical Care", "Avinashi Road", "Coimbatore", "Coimbatore", "641014", "11.025", "77.012", "hospital", "15", "ICU, Trauma, Blood Bank"],
        ["H-IMP-002", "Peelamedu Health Clinic", "Hope College", "Coimbatore", "Coimbatore", "641004", "11.031", "77.020", "clinic", "2", "General Consultation"],
    ]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    summary = DatasetImporter.import_hospitals(str(csv_file), db=db, dry_run=False)
    assert summary.valid_rows == 2
    assert summary.new_records_inserted == 2

    h = db.query(Hospital).filter(Hospital.id == "H-IMP-001").first()
    assert h is not None
    assert h.category == "hospital"
    assert h.emergency_bays == 15
    assert h.district == "Coimbatore"
    assert "Trauma" in h.services


def test_import_blood_banks_success(db, tmp_path):
    csv_file = tmp_path / "blood_banks.csv"
    headers = ["blood_bank_id", "name", "address", "city", "district", "pincode", "latitude", "longitude", "phone", "services"]
    rows = [
        ["BB-IMP-001", "LifeLink Regional Blood Center", "Trichy Road", "Coimbatore", "Coimbatore", "641018", "11.005", "76.985", "0422-2223333", "Whole Blood, Platelets, Plasma"],
    ]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    summary = DatasetImporter.import_blood_banks(str(csv_file), db=db, dry_run=False)
    assert summary.valid_rows == 1
    assert summary.new_records_inserted == 1

    bb = db.query(BloodBank).filter(BloodBank.id == "BB-IMP-001").first()
    assert bb is not None
    assert bb.name == "LifeLink Regional Blood Center"
    assert bb.city == "Coimbatore"
    assert bb.pincode == "641018"
    assert "Platelets" in bb.services


def test_blood_banks_api_endpoints(client, db):
    # Seed one test blood bank and one blood inventory in-memory
    bb = BloodBank(
        id="BB-TEST-001",
        name="Coimbatore Rotary Blood Bank",
        address="Race Course Road",
        city="Coimbatore",
        district="Coimbatore",
        pincode="641018",
        lat=11.011,
        lng=76.972,
        contact_number="0422-123456",
        services="Component Separation, Whole Blood",
    )
    db.add(bb)

    inv = BloodInventory(
        id="INV-TEST-001",
        blood_bank_id="BB-TEST-001",
        blood_group="O+",
        units_available=8,
        units_reserved=2,
    )
    db.add(inv)
    db.commit()

    # 1. List blood banks
    r = client.get("/api/v1/blood-banks")
    assert r.status_code == 200
    bbs = r.json()
    assert any(b["id"] == "BB-TEST-001" for b in bbs)

    # 2. Filter blood banks by district
    r2 = client.get("/api/v1/blood-banks?district=Coimbatore")
    assert r2.status_code == 200
    assert len(r2.json()) >= 1

    # 3. Get single blood bank
    r3 = client.get("/api/v1/blood-banks/BB-TEST-001")
    assert r3.status_code == 200
    assert r3.json()["name"] == "Coimbatore Rotary Blood Bank"

    # 4. Get blood bank inventory
    r4 = client.get("/api/v1/blood-banks/BB-TEST-001/inventory")
    assert r4.status_code == 200
    data = r4.json()
    assert data["bloodBankId"] == "BB-TEST-001"
    assert data["bloodInventory"]["O+"] == 8
    assert data["bloodInventory"]["A+"] == 0
    assert data["totalUnitsAvailable"] == 8


def test_hospitals_inventory_with_empty_and_populated_db(client, db):
    h = Hospital(
        id="H-TEST-INV",
        name="Test Coimbatore General",
        address="Mettupalayam Road",
        city="Coimbatore",
        district="Coimbatore",
        pincode="641043",
        lat=11.040,
        lng=76.940,
        type="general",
        category="hospital",
        emergency_bays=10,
    )
    db.add(h)
    db.commit()

    # Inventory when none seeded -> all 0s, emergency bays mapped accurately
    r1 = client.get("/api/v1/hospitals/H-TEST-INV/inventory")
    assert r1.status_code == 200
    inv1 = r1.json()
    assert inv1["bloodInventory"]["O+"] == 0
    assert inv1["bloodInventory"]["A-"] == 0
    assert inv1["emergencyBaysTotal"] == 10
    assert inv1["emergencyBaysAvailable"] == 5

    # Add verified inventory record
    inv_rec = BloodInventory(
        id="INV-H-001",
        hospital_id="H-TEST-INV",
        blood_group="B+",
        units_available=15,
    )
    db.add(inv_rec)
    db.commit()

    r2 = client.get("/api/v1/hospitals/H-TEST-INV/inventory")
    assert r2.status_code == 200
    inv2 = r2.json()
    assert inv2["bloodInventory"]["B+"] == 15
    assert inv2["bloodInventory"]["O+"] == 0


def test_import_synthetic_dataset_rules(db, tmp_path):
    csv_file = tmp_path / "synthetic_demo.csv"
    headers = [
        "donor_id", "full_name", "age", "gender", "city", "district", "locality",
        "pincode", "blood_group", "availability", "availability_rule", "phone_number",
        "phone_assignment_group", "last_contact_status", "consent_status", "record_type", "production_ready"
    ]
    rows = [
        ["DEMO-001", "Meena Priya", "32", "Female", "Coimbatore", "Coimbatore", "Town Hall", "641001", "AB-", "Pending response", "Rule", "9003350486", "GROUP-1", "Not contacted", "DEMO ONLY - consent not collected", "SYNTHETIC DEMO RECORD - NOT A REAL DONOR", "NO"],
        ["DEMO-002", "Rajesh Kumar", "28", "Male", "Coimbatore", "Coimbatore", "Peelamedu", "641004", "O+", "Pending response", "Rule", "9003350486", "GROUP-1", "Not contacted", "DEMO ONLY - consent not collected", "SYNTHETIC DEMO RECORD - NOT A REAL DONOR", "NO"],
    ]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    summary = DatasetImporter.import_donors(str(csv_file), db=db, dry_run=False)

    assert summary.valid_rows == 2
    assert summary.unique_phone_numbers == 1
    assert summary.repeated_phone_rows == 1

    d1 = db.query(Donor).filter(Donor.id == "DEMO-001").first()
    assert d1 is not None
    # 1. Synthetic provenance
    assert d1.is_synthetic is True
    assert d1.data_provenance == "synthetic_demo"
    # 2. Availability safeguard: Pending response must NEVER be marked available
    assert d1.status == "unavailable"
    # 3. Clinical Eligibility safeguard: Unverified donor must NEVER be assumed eligible
    assert d1.eligibility == "pending_review"
    # 4. Simulated Coordinates: Computed for Coimbatore locality
    assert d1.simulated_coordinates is True
    assert 10.8 <= d1.lat <= 11.2
    assert 76.8 <= d1.lng <= 77.2


def test_import_duplicate_donor_id_in_csv(db, tmp_path):
    csv_file = tmp_path / "dup_id.csv"
    headers = ["donor_id", "full_name", "blood_group", "city"]
    rows = [
        ["D-DUP-SAME", "First Occurrence", "O+", "Coimbatore"],
        ["D-DUP-SAME", "Second Occurrence", "O+", "Coimbatore"],
    ]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    summary = DatasetImporter.import_donors(str(csv_file), db=db, dry_run=False)
    assert summary.valid_rows == 1
    assert summary.invalid_rows == 1
    assert any("Duplicate Donor ID" in err for err in summary.errors)


def test_production_matching_excludes_synthetic_donors(db):
    from app.services.donor_service import DonorService
    from app.models.emergency import Emergency

    # Create emergency in Coimbatore
    emerg = Emergency(
        id="EMERG-MATCH-001",
        patient_id="P-001",
        hospital_id="city-hospital-001",
        hospital_name="City Hospital",
        type="blood",
        priority="critical",
        status="active",
        created_at="2026-10-25T12:00:00Z",
        updated_at="2026-10-25T12:00:00Z",
        description="Emergency blood requirement",
        blood_group="O+",
        location_lat=11.0183,
        location_lng=76.9639,
    )

    db.add(emerg)

    # Production donor (eligible, available)
    prod_donor = Donor(
        id="D-PROD-MATCH",
        blood_group="O+",
        city="Coimbatore",
        lat=11.0200,
        lng=76.9650,
        status="available",
        eligibility="eligible",
        is_synthetic=False,
        data_provenance="production",
        location_consent_granted=True,
    )
    db.add(prod_donor)

    # Synthetic donor (also O+, near emergency)
    synth_donor = Donor(
        id="D-SYNTH-MATCH",
        blood_group="O+",
        city="Coimbatore",
        lat=11.0190,
        lng=76.9640,
        status="available",
        eligibility="eligible",
        is_synthetic=True,
        data_provenance="synthetic_demo",
    )
    db.add(synth_donor)
    db.commit()

    # 1. Production matching: Must exclude synthetic donor
    res_prod = DonorService.get_ranked_donors(db, emergency_id="EMERG-MATCH-001", demo_mode=False)
    prod_ids = [d.id for d in res_prod.donors]
    assert "D-PROD-MATCH" in prod_ids
    assert "D-SYNTH-MATCH" not in prod_ids

    # 2. Demo matching: Includes both
    res_demo = DonorService.get_ranked_donors(db, emergency_id="EMERG-MATCH-001", demo_mode=True)
    demo_ids = [d.id for d in res_demo.donors]
    assert "D-PROD-MATCH" in demo_ids
    assert "D-SYNTH-MATCH" in demo_ids


def test_dispatch_safety_and_failure_handling(db, monkeypatch):
    from app.services.donor_service import DonorService
    from app.models.emergency import Emergency
    from app.models.interaction import DonorEmergencyInteraction
    from app.simulation.mock_notifications import mock_notification_provider

    emerg = Emergency(
        id="EMERG-DISPATCH-SAFE",
        patient_id="P-002",
        hospital_id="city-hospital-001",
        hospital_name="City Hospital",
        type="blood",
        priority="critical",
        status="active",
        created_at="2026-10-25T12:00:00Z",
        updated_at="2026-10-25T12:00:00Z",
        description="Emergency blood requirement",
        blood_group="A+",
        location_lat=11.0183,
        location_lng=76.9639,
    )
    db.add(emerg)

    donor = Donor(
        id="D-DISP-001",
        blood_group="A+",
        city="Coimbatore",
        lat=11.0190,
        lng=76.9640,
        status="available",
        eligibility="eligible",
        is_synthetic=False,
        data_provenance="production",
    )
    db.add(donor)
    db.commit()

    # Simulate provider failure
    def mock_fail(*args, **kwargs):
        raise RuntimeError("Simulated network/provider timeout")

    monkeypatch.setattr(mock_notification_provider, "dispatch", mock_fail)

    res = DonorService.dispatch_emergency_donor_batch(db, emergency_id="EMERG-DISPATCH-SAFE", batch_size=1)
    assert res.donorsContactedCount == 0

    inter = db.query(DonorEmergencyInteraction).filter(DonorEmergencyInteraction.donor_id == "D-DISP-001").first()
    assert inter is not None
    assert inter.contact_status == "failed"
    assert inter.acceptance_status == "unreachable"


def test_response_validation_and_synthetic_separation(db):
    from app.services.donor_service import DonorService
    from app.models.emergency import Emergency
    from app.models.interaction import DonorEmergencyInteraction
    from fastapi import HTTPException

    emerg = Emergency(
        id="EMERG-RESP-001",
        patient_id="P-003",
        hospital_id="city-hospital-001",
        hospital_name="City Hospital",
        type="blood",
        priority="critical",
        status="active",
        created_at="2026-10-25T12:00:00Z",
        updated_at="2026-10-25T12:00:00Z",
        description="Emergency blood requirement",
        blood_group="B+",
        location_lat=11.0183,
        location_lng=76.9639,
    )
    db.add(emerg)




    synth_donor = Donor(
        id="D-SYNTH-RESP",
        blood_group="B+",
        city="Coimbatore",
        status="contacted",
        eligibility="pending_review",
        is_synthetic=True,
        data_provenance="synthetic_demo",
    )
    db.add(synth_donor)

    # Active pending interaction for synthetic donor
    inter = DonorEmergencyInteraction(
        id="dint-synth-001",
        emergency_id="EMERG-RESP-001",
        donor_id="D-SYNTH-RESP",
        selected_at="2026-10-25T12:00:00Z",
        distance_km=3.5,
        time_of_day_hours=12.0,
        day_of_week=0,
        emergency_priority="critical",
        contact_status="attempted",
        response_status="pending",
        acceptance_status="pending",
        completion_status="pending",
        is_synthetic=True,
        data_provenance="synthetic_demo",
        created_at="2026-10-25T12:00:00Z",
        updated_at="2026-10-25T12:00:00Z",
    )
    db.add(inter)
    db.commit()


    # 1. Invalid status choice raises HTTP 400
    with pytest.raises(HTTPException) as exc:
        DonorService.record_donor_response(db, donor_id="D-SYNTH-RESP", status_choice="invalid_status")
    assert exc.value.status_code == 400

    # 2. Simulated acceptance: Must be marked simulated_accepted and NOT count as real production acceptance
    DonorService.record_donor_response(db, donor_id="D-SYNTH-RESP", status_choice="accepted")
    db.refresh(inter)
    assert inter.acceptance_status == "simulated_accepted"

    # 3. Workflow status check: totalAccepted must remain 0
    wf = DonorService.get_emergency_workflow_status(db, emergency_id="EMERG-RESP-001")
    assert wf.totalAccepted == 0
    assert wf.targetReached is False

