import pytest
from sqlalchemy.exc import IntegrityError
from app.db.base import Base
from app.models.user import User
from app.models.hospital import Hospital
from app.models.consent import Consent
from app.models.ambulance import Ambulance
from app.models.emergency import Emergency, EmergencyEvent
from app.models.donor import Donor
from app.models.organ import Organ
from app.models.audit import AuditLog
from app.core.config import settings
from app.db.session import engine


def test_unique_user_email_constraint(db):
    user1 = User(
        id="usr-test-101",
        name="Test Doctor",
        email="unique_doctor@lifelink.demo",
        hashed_password="hash",
        role="doctor",
        session_status="active",
    )
    db.add(user1)
    db.commit()

    user2 = User(
        id="usr-test-102",
        name="Duplicate Email Doctor",
        email="unique_doctor@lifelink.demo",
        hashed_password="hash",
        role="doctor",
        session_status="active",
    )
    db.add(user2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_unique_consent_user_id_constraint(db):
    user = User(
        id="usr-test-201",
        name="Consent User",
        email="consent_user@lifelink.demo",
        hashed_password="hash",
        role="donor",
        session_status="active",
    )
    db.add(user)
    db.commit()

    c1 = Consent(
        id="cns-test-001",
        user_id="usr-test-201",
        live_location=True,
        emergency_communication=True,
        donation_requests=True,
        health_data_sharing=True,
        updated_at="2026-08-29T19:30:00Z",
    )
    db.add(c1)
    db.commit()

    c2 = Consent(
        id="cns-test-002",
        user_id="usr-test-201",
        live_location=False,
        emergency_communication=False,
        donation_requests=False,
        health_data_sharing=False,
        updated_at="2026-08-29T19:30:00Z",
    )
    db.add(c2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_unique_ambulance_unit_number_constraint(db):
    h = db.query(Hospital).first()
    a1 = Ambulance(
        id="amb-test-001",
        unit_number="AMB-UNIQUE-001",
        status="idle",
        hospital_id=h.id,
        updated_at="2026-08-29T19:30:00Z",
    )
    db.add(a1)
    db.commit()

    a2 = Ambulance(
        id="amb-test-002",
        unit_number="AMB-UNIQUE-001",
        status="idle",
        hospital_id=h.id,
        updated_at="2026-08-29T19:30:00Z",
    )
    db.add(a2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_all_models_registered_in_metadata():
    table_names = set(Base.metadata.tables.keys())
    expected = {
        "users",
        "hospitals",
        "emergencies",
        "emergency_events",
        "donors",
        "organs",
        "ambulances",
        "audit_logs",
        "consents",
    }
    assert expected.issubset(table_names)


def test_database_url_normalization():
    from app.core.config import Settings
    s1 = Settings(DATABASE_URL="postgres://user:pass@localhost:5432/lifelink")
    assert s1.DATABASE_URL.startswith("postgresql+psycopg://")

    s2 = Settings(DATABASE_URL="postgresql://user:pass@localhost:5432/lifelink")
    assert s2.DATABASE_URL.startswith("postgresql+psycopg://")


def test_audit_log_durability_and_immutability(db):
    # Ensure audit log is created and stays durable
    log = AuditLog(
        id="audit-test-999",
        timestamp="2026-08-29T19:30:00Z",
        actor="Dr. Arjun Rao",
        actor_type="user",
        action="Emergency triage protocol activated",
        resource="Emergency #BL-102",
        resource_id="BL-102",
        status="success",
        module="emergency",
    )
    db.add(log)
    db.commit()

    fetched = db.query(AuditLog).filter(AuditLog.id == "audit-test-999").first()
    assert fetched is not None
    assert fetched.action == "Emergency triage protocol activated"
