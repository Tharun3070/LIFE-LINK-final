"""Tests for User Self-Registration Workflow, Validation, and Privilege Escalation Prevention."""
import pytest
from app.models.user import User
from app.models.donor import Donor
from app.models.consent import Consent
from app.core.security import verify_password


def test_successful_donor_registration(client, db):
    """New donor registers, gets access token, and donor/consent records are initialized."""
    email = "new_donor_2026@lifelink.org"
    password = "SecurePassword123!"

    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Jane Donor",
            "email": email,
            "password": password,
            "role": "donor",
            "bloodGroup": "O-",
            "phone": "+919876543210",
            "city": "Bangalore",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert "token" in data
    assert "refreshToken" in data
    assert data["user"]["email"] == email
    assert data["user"]["role"] == "donor"

    # Verify DB user record
    user_db = db.query(User).filter(User.email == email).first()
    assert user_db is not None
    assert user_db.name == "Jane Donor"
    assert verify_password(password, user_db.hashed_password)

    # Verify Donor profile record created
    donor_db = db.query(Donor).filter(Donor.user_id == user_db.id).first()
    assert donor_db is not None
    assert donor_db.blood_group == "O-"
    assert donor_db.status == "available"
    assert donor_db.is_synthetic is False

    # Verify Consent record created
    consent_db = db.query(Consent).filter(Consent.user_id == user_db.id).first()
    assert consent_db is not None
    assert consent_db.emergency_communication is True


def test_successful_patient_registration(client, db):
    """New patient self-registers successfully."""
    email = "new_patient_2026@lifelink.org"
    password = "SecurePassword123!"

    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "John Patient",
            "email": email,
            "password": password,
            "role": "patient",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["user"]["role"] == "patient"
    assert data["user"]["email"] == email


def test_login_after_registration(client):
    """Newly registered account can authenticate immediately via /api/v1/auth/login."""
    email = "login_test_user@lifelink.org"
    password = "MyStrongPassword2026!"

    # 1. Register
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Test Login User",
            "email": email,
            "password": password,
            "role": "donor",
            "bloodGroup": "A+",
        },
    )
    assert reg_resp.status_code == 201

    # 2. Login
    login_resp = client.post(
        "/api/v1/auth/login",
        json={
            "identifier": email,
            "password": password,
        },
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["token"]

    # 3. Access authenticated endpoint
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == email


def test_duplicate_email_registration_fails(client):
    """Duplicate email registration is strictly rejected with HTTP 409 Conflict."""
    email = "duplicate_check@lifelink.org"
    payload = {
        "name": "First User",
        "email": email,
        "password": "Password12345!",
        "role": "donor",
    }

    resp1 = client.post("/api/v1/auth/register", json=payload)
    assert resp1.status_code == 201

    resp2 = client.post("/api/v1/auth/register", json=payload)
    assert resp2.status_code == 409
    err_text = resp2.json().get("message") or resp2.json().get("detail", "")
    assert "already exists" in err_text.lower()


@pytest.mark.parametrize("forbidden_role", ["admin", "hospital_staff", "transplant_coordinator", "superadmin"])
def test_privilege_escalation_blocked(client, forbidden_role):
    """Public registration cannot assign administrator or hospital internal staff roles."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": f"Hacker {forbidden_role}",
            "email": f"hacker_{forbidden_role}@malicious.com",
            "password": "HackingPassword123!",
            "role": forbidden_role,
        },
    )
    assert response.status_code == 403
    err_text = response.json().get("message") or response.json().get("detail", "")
    assert "prohibited" in err_text.lower()



def test_invalid_registration_inputs(client):
    """Validation rejects short passwords, invalid emails, and empty names."""
    # 1. Short password (< 8 chars)
    r1 = client.post(
        "/api/v1/auth/register",
        json={"name": "Alice", "email": "alice@test.com", "password": "short"},
    )
    assert r1.status_code == 422

    # 2. Invalid email format
    r2 = client.post(
        "/api/v1/auth/register",
        json={"name": "Alice", "email": "not-an-email", "password": "ValidPassword123!"},
    )
    assert r2.status_code == 422

    # 3. Empty name
    r3 = client.post(
        "/api/v1/auth/register",
        json={"name": " ", "email": "alice@test.com", "password": "ValidPassword123!"},
    )
    assert r3.status_code == 422
