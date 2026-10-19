"""Tests for Priority 1: Patient-to-Emergency Foreign Key Migration and Object-Level Authorization."""
import pytest
from app.models.user import User
from app.models.emergency import Emergency
from app.models.hospital import Hospital
from app.core.security import create_access_token, get_password_hash


def test_patient_me_standby_when_unlinked(client, patient_token):
    """A patient with no linked emergency receives null and sees the truthful standby state."""
    response = client.get(
        "/api/v1/emergencies/patient/me",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert response.status_code == 200
    assert response.json() is None


def test_emergency_creation_with_patient_id(client, doctor_token, db):
    """Doctor creates an emergency associated with an authorized patient."""
    patient = db.query(User).filter(User.role == "patient").first()
    assert patient is not None
    hospital = db.query(Hospital).first()
    assert hospital is not None

    payload = {
        "type": "blood",
        "priority": "critical",
        "hospitalId": hospital.id,
        "hospitalName": hospital.name,
        "description": "Urgent O- blood needed for patient",
        "bloodGroup": "O-",
        "unitsRequired": 2,
        "patientId": patient.id,
    }

    response = client.post(
        "/api/v1/emergencies",
        json=payload,
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["patientId"] == patient.id
    emergency_id = data["id"]

    # Verify patient can retrieve via patient/me
    patient_token = create_access_token(subject=patient.id, role=patient.role)
    me_resp = client.get(
        "/api/v1/emergencies/patient/me",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data is not None
    assert me_data["id"] == emergency_id
    assert me_data["patientId"] == patient.id


def test_patient_cross_isolation_forbidden(client, doctor_token, db):
    """A patient cannot access another patient's emergency; object-level authorization returns 403."""
    patient1 = db.query(User).filter(User.role == "patient").first()
    assert patient1 is not None
    hospital = db.query(Hospital).first()
    assert hospital is not None

    # Create patient 2
    patient2 = User(
        id="usr-pat-002-test",
        email="patient2.test@example.com",
        name="Second Test Patient",
        hashed_password=get_password_hash("patient123"),
        role="patient",
        is_verified=True,
    )
    db.add(patient2)
    db.commit()

    # Doctor creates emergency for patient 1
    create_resp = client.post(
        "/api/v1/emergencies",
        json={
            "type": "blood",
            "priority": "high",
            "hospitalId": hospital.id,
            "hospitalName": hospital.name,
            "description": "Patient 1 emergency",
            "bloodGroup": "A+",
            "unitsRequired": 1,
            "patientId": patient1.id,
        },
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert create_resp.status_code == 200
    emg_id = create_resp.json()["id"]

    # Patient 2 tries to access Patient 1's emergency -> 403 Forbidden
    patient2_token = create_access_token(subject=patient2.id, role=patient2.role)
    unauth_resp = client.get(
        f"/api/v1/emergencies/{emg_id}",
        headers={"Authorization": f"Bearer {patient2_token}"},
    )
    assert unauth_resp.status_code == 403
    assert "Access forbidden" in unauth_resp.json()["message"]


def test_patient_list_emergencies_filtered(client, doctor_token, db):
    """Listing emergencies as a patient only returns emergencies linked to that patient."""
    patient = db.query(User).filter(User.role == "patient").first()
    hospital = db.query(Hospital).first()
    assert hospital is not None

    # Create an unlinked emergency
    client.post(
        "/api/v1/emergencies",
        json={
            "type": "blood",
            "priority": "medium",
            "hospitalId": hospital.id,
            "hospitalName": hospital.name,
            "description": "Unlinked emergency",
            "bloodGroup": "B+",
            "unitsRequired": 1,
        },
        headers={"Authorization": f"Bearer {doctor_token}"},
    )

    # Create linked emergency for patient
    client.post(
        "/api/v1/emergencies",
        json={
            "type": "organ",
            "priority": "critical",
            "hospitalId": hospital.id,
            "hospitalName": hospital.name,
            "description": "Kidney match",
            "organType": "kidney",
            "patientId": patient.id,
        },
        headers={"Authorization": f"Bearer {doctor_token}"},
    )

    # Patient listing emergencies sees only their own linked emergency
    patient_token = create_access_token(subject=patient.id, role=patient.role)
    list_resp = client.get(
        "/api/v1/emergencies",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert list_resp.status_code == 200
    emergencies = list_resp.json()
    assert len(emergencies) >= 1
    assert all(e.get("patientId") == patient.id for e in emergencies)


def test_patient_direct_emergency_creation_blocked_by_rbac(client, patient_token, db):
    """Platform emergency dispatch creation is restricted to clinical staff; patient direct creation returns 403."""
    hospital = db.query(Hospital).first()
    assert hospital is not None

    response = client.post(
        "/api/v1/emergencies",
        json={
            "type": "ambulance",
            "priority": "critical",
            "hospitalId": hospital.id,
            "hospitalName": hospital.name,
            "description": "Patient direct creation attempt",
        },
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert response.status_code == 403


def test_staff_creation_without_patient_association(client, staff_token, db):
    """Clinical staff can create an emergency without an initial patient association."""
    hospital = db.query(Hospital).first()
    assert hospital is not None

    response = client.post(
        "/api/v1/emergencies",
        json={
            "type": "blood",
            "priority": "high",
            "hospitalId": hospital.id,
            "hospitalName": hospital.name,
            "description": "Trauma center reserve unit request",
            "bloodGroup": "AB+",
            "unitsRequired": 3,
        },
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    assert response.status_code == 200
    assert response.json()["patientId"] is None


def test_alembic_migration_0004_upgrade_downgrade(tmp_path):
    """Test Alembic upgrade to revision 0004 and downgrade to 0003 on an isolated temporary database."""
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import create_engine, inspect

    db_path = tmp_path / "test_migration_isolated.db"
    db_url = f"sqlite:///{db_path}"

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)

    # Run upgrade to 0004
    command.upgrade(cfg, "0004_patient_emergency_linkage")

    # Inspect table to verify emergencies.patient_id column exists
    engine = create_engine(db_url)
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns("emergencies")]
    assert "patient_id" in columns

    # Run downgrade to 0003
    command.downgrade(cfg, "0003_donor_synthetic_provenance")

    engine.dispose()
    engine2 = create_engine(db_url)
    inspector2 = inspect(engine2)
    columns_after = [col["name"] for col in inspector2.get_columns("emergencies")]
    assert "patient_id" not in columns_after
    engine2.dispose()


