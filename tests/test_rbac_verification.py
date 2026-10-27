"""Complete Role-Based Access Control (RBAC) and Professional Verification Test Suite.

Covers the 20 test specifications from LifeLink RBAC requirements:
1. Patient registration assigns the correct role.
2. Doctor registration creates a pending account.
3. Driver registration creates a pending account.
4. Public registration cannot create an admin.
5. Duplicate email registration is rejected.
6. Passwords are securely hashed.
7. Invalid login is rejected.
8. Protected endpoints reject unauthenticated users.
9. Patients cannot access admin endpoints.
10. Doctors cannot access admin endpoints.
11. Drivers cannot access admin endpoints.
12. Pending doctors cannot use protected doctor functionality.
13. Pending drivers cannot use protected driver functionality.
14. Administrators can approve eligible accounts.
15. Unauthorized users cannot approve accounts.
16. Users cannot approve themselves.
17. Users cannot modify their own role.
18. Rejected professionals cannot use protected professional functionality.
19. Unauthorized access to private records is prevented.
20. Existing application tests continue to pass.
"""
import pytest
from app.models.user import User
from app.core.security import verify_password, create_access_token


def get_error_message(resp):
    data = resp.json()
    return str(data.get("message") or data.get("detail") or "").lower()



# 1. Patient registration assigns correct role and verified status
def test_01_patient_registration_assigns_correct_role(client, db):
    email = "patient_rbac_test@lifelink.org"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Alex Patient",
            "email": email,
            "password": "Password123!",
            "role": "patient",
            "phone": "+91-9876543210",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["user"]["role"] == "patient"
    assert data["user"]["isVerified"] is True
    assert data["user"]["verificationStatus"] == "not_required"

    user_db = db.query(User).filter(User.email == email).first()
    assert user_db is not None
    assert user_db.role == "patient"
    assert user_db.is_verified is True
    assert user_db.verification_status == "not_required"


# 2. Doctor registration creates a pending account
def test_02_doctor_registration_creates_pending_account(client, db):
    email = "dr_pending@lifelink.org"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Dr. Sarah Jenkins",
            "email": email,
            "password": "SecureDoctorPass123!",
            "role": "doctor",
            "phone": "+91-9876500001",
            "medicalLicenseNumber": "MCI-KA-2026-9876",
            "hospitalName": "St. Jude Trauma Care",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["user"]["role"] == "doctor"
    assert data["user"]["isVerified"] is False
    assert data["user"]["verificationStatus"] == "pending"

    user_db = db.query(User).filter(User.email == email).first()
    assert user_db is not None
    assert user_db.role == "doctor"
    assert user_db.is_verified is False
    assert user_db.verification_status == "pending"
    assert user_db.medical_license_number == "MCI-KA-2026-9876"
    assert user_db.hospital_name == "St. Jude Trauma Care"


# 3. Driver registration creates a pending account
def test_03_driver_registration_creates_pending_account(client, db):
    email = "driver_pending@lifelink.org"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Kiran Pilot",
            "email": email,
            "password": "DriverPassword123!",
            "role": "ambulance_driver",
            "phone": "+91-9876500002",
            "drivingLicenseNumber": "KA-01-2020-0012345",
            "vehicleId": "AMB-BLR-108",
            "organization": "City Ambulance Dispatch",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["user"]["role"] in ["ambulance_driver", "ambulance_operator"]
    assert data["user"]["isVerified"] is False
    assert data["user"]["verificationStatus"] == "pending"

    user_db = db.query(User).filter(User.email == email).first()
    assert user_db is not None
    assert user_db.is_verified is False
    assert user_db.verification_status == "pending"
    assert user_db.driving_license_number == "KA-01-2020-0012345"
    assert user_db.vehicle_id == "AMB-BLR-108"


# 4. Public registration cannot create an admin
def test_04_public_registration_cannot_create_admin(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Malicious Admin",
            "email": "hacker_admin@domain.com",
            "password": "AdminPassword123!",
            "role": "admin",
        },
    )
    assert response.status_code == 403
    assert "prohibited" in get_error_message(response)


# 5. Duplicate email registration is rejected
def test_05_duplicate_email_registration_rejected(client):
    email = "unique_patient@lifelink.org"
    payload = {
        "name": "First Patient",
        "email": email,
        "password": "ValidPassword123!",
        "role": "patient",
    }
    resp1 = client.post("/api/v1/auth/register", json=payload)
    assert resp1.status_code == 201

    resp2 = client.post("/api/v1/auth/register", json=payload)
    assert resp2.status_code == 409
    assert "already exists" in get_error_message(resp2)



# 6. Passwords are securely hashed
def test_06_passwords_are_securely_hashed(client, db):
    email = "hash_check@lifelink.org"
    plain_password = "MyComplexPassword2026!"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Hash User",
            "email": email,
            "password": plain_password,
            "role": "patient",
        },
    )
    assert response.status_code == 201
    user_db = db.query(User).filter(User.email == email).first()
    assert user_db.hashed_password != plain_password
    assert user_db.hashed_password.startswith("$2b$") or user_db.hashed_password.startswith("$2a$")
    assert verify_password(plain_password, user_db.hashed_password)


# 7. Invalid login is rejected
def test_07_invalid_login_is_rejected(client):
    # Nonexistent user
    r1 = client.post(
        "/api/v1/auth/login",
        json={"identifier": "nonexistent@user.com", "password": "WrongPassword123!"},
    )
    assert r1.status_code == 401

    # Wrong password for existing user
    r2 = client.post(
        "/api/v1/auth/login",
        json={"identifier": "doctor@lifelink.demo", "password": "incorrect_password"},
    )
    assert r2.status_code == 401


# 8. Protected endpoints reject unauthenticated users
def test_08_protected_endpoints_reject_unauthenticated_users(client):
    endpoints = [
        ("GET", "/api/v1/users"),
        ("GET", "/api/v1/users/me"),
        ("GET", "/api/v1/users/pending-verification"),
        ("POST", "/api/v1/emergencies"),
        ("POST", "/api/v1/ambulances/amb-042/location"),
        ("POST", "/api/v1/ambulances/amb-042/status"),
    ]
    for method, path in endpoints:
        if method == "GET":
            r = client.get(path)
        else:
            r = client.post(path, json={})
        assert r.status_code == 401, f"Expected 401 for unauthenticated {method} {path}, got {r.status_code}"


# 9. Patients cannot access admin endpoints
def test_09_patients_cannot_access_admin_endpoints(client, patient_token):
    headers = {"Authorization": f"Bearer {patient_token}"}
    r1 = client.get("/api/v1/users", headers=headers)
    assert r1.status_code == 403
    r2 = client.get("/api/v1/users/pending-verification", headers=headers)
    assert r2.status_code == 403


# 10. Doctors cannot access admin endpoints
def test_10_doctors_cannot_access_admin_endpoints(client, doctor_token):
    headers = {"Authorization": f"Bearer {doctor_token}"}
    r1 = client.get("/api/v1/users", headers=headers)
    assert r1.status_code == 403
    r2 = client.get("/api/v1/users/pending-verification", headers=headers)
    assert r2.status_code == 403


# 11. Drivers cannot access admin endpoints
def test_11_drivers_cannot_access_admin_endpoints(client, ambulance_token):
    headers = {"Authorization": f"Bearer {ambulance_token}"}
    r1 = client.get("/api/v1/users", headers=headers)
    assert r1.status_code == 403
    r2 = client.get("/api/v1/users/pending-verification", headers=headers)
    assert r2.status_code == 403


# 12. Pending doctors cannot use protected doctor functionality
def test_12_pending_doctors_cannot_use_doctor_functionality(client):
    # Register pending doctor
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Dr. Unverified",
            "email": "dr_unverified@lifelink.org",
            "password": "DoctorPassword123!",
            "role": "doctor",
            "medicalLicenseNumber": "MCI-PENDING-001",
        },
    )
    assert reg_resp.status_code == 201
    pending_token = reg_resp.json()["token"]

    # Attempt to create an emergency
    headers = {"Authorization": f"Bearer {pending_token}"}
    resp = client.post(
        "/api/v1/emergencies",
        headers=headers,
        json={
            "type": "blood",
            "priority": "critical",
            "hospitalId": "city-hospital-001",
            "description": "Unauthorized attempt by pending doctor",
            "bloodGroup": "O-",
            "unitsRequired": 2,
        },
    )
    assert resp.status_code == 403
    assert "pending verification" in get_error_message(resp)


# 13. Pending drivers cannot use protected driver functionality
def test_13_pending_drivers_cannot_use_driver_functionality(client):
    # Register pending driver
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Unverified Driver",
            "email": "driver_unverified@lifelink.org",
            "password": "DriverPassword123!",
            "role": "ambulance_driver",
            "drivingLicenseNumber": "DL-PENDING-99",
            "vehicleId": "AMB-99",
        },
    )
    assert reg_resp.status_code == 201
    pending_token = reg_resp.json()["token"]

    # Attempt to update ambulance location
    headers = {"Authorization": f"Bearer {pending_token}"}
    r_loc = client.post(
        "/api/v1/ambulances/amb-042/location",
        headers=headers,
        json={"lat": 12.9716, "lng": 77.5946, "heading": 180.0, "speedKmh": 40.0},
    )
    assert r_loc.status_code == 403
    assert "pending verification" in get_error_message(r_loc)

    # Attempt to update ambulance status
    r_stat = client.post(
        "/api/v1/ambulances/amb-042/status",
        headers=headers,
        json={"status": "dispatched"},
    )
    assert r_stat.status_code == 403
    assert "pending verification" in get_error_message(r_stat)


# 14. Administrators can approve eligible accounts
def test_14_administrators_can_approve_eligible_accounts(client, admin_token, db):
    # 1. Register a doctor who starts pending
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Dr. To Be Approved",
            "email": "dr_approve_me@lifelink.org",
            "password": "DoctorPassword123!",
            "role": "doctor",
            "medicalLicenseNumber": "MCI-VERIFY-1234",
            "hospitalName": "City General Hospital",
        },
    )
    assert reg_resp.status_code == 201
    doctor_data = reg_resp.json()["user"]
    doctor_id = doctor_data["id"]
    doctor_token = reg_resp.json()["token"]

    # Verify pending queue lists this doctor
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    pending_resp = client.get("/api/v1/users/pending-verification", headers=admin_headers)
    assert pending_resp.status_code == 200
    pending_list = pending_resp.json()
    assert any(u["id"] == doctor_id for u in pending_list)

    # 2. Administrator approves the doctor
    verify_resp = client.post(
        f"/api/v1/users/{doctor_id}/verify",
        headers=admin_headers,
        json={"status": "approved", "notes": "Medical license verified with Karnataka Medical Council"},
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["verificationStatus"] == "approved"
    assert verify_resp.json()["isVerified"] is True

    # 3. Now the approved doctor can use protected doctor functionality
    doc_headers = {"Authorization": f"Bearer {doctor_token}"}
    emg_resp = client.post(
        "/api/v1/emergencies",
        headers=doc_headers,
        json={
            "type": "blood",
            "priority": "critical",
            "hospitalId": "city-hospital-001",
            "description": "Emergency created by newly approved doctor",
            "bloodGroup": "A+",
            "unitsRequired": 1,
        },
    )
    assert emg_resp.status_code == 200
    assert emg_resp.json()["type"] == "blood"


# 15. Unauthorized users cannot approve accounts
def test_15_unauthorized_users_cannot_approve_accounts(client, patient_token, doctor_token, ambulance_token):
    target_user_id = "usr-some-user"
    for token, role_name in [(patient_token, "patient"), (doctor_token, "doctor"), (ambulance_token, "driver")]:
        resp = client.post(
            f"/api/v1/users/{target_user_id}/verify",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "approved", "notes": "Unauthorized attempt"},
        )
        assert resp.status_code == 403, f"{role_name} was not rejected with 403 on approval endpoint"


# 16. Users cannot approve themselves
def test_16_users_cannot_approve_themselves(client, admin_token, db):
    admin_user = db.query(User).filter(User.role == "admin").first()
    assert admin_user is not None

    resp = client.post(
        f"/api/v1/users/{admin_user.id}/verify",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "approved", "notes": "Self approval attempt"},
    )
    assert resp.status_code == 400
    assert "cannot" in get_error_message(resp)


# 17. Users cannot modify their own role
def test_17_users_cannot_modify_their_own_role(client, patient_token, db):
    # Patient attempts to modify their role to admin via profile update
    headers = {"Authorization": f"Bearer {patient_token}"}
    resp = client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"role": "admin", "verificationStatus": "approved", "name": "Alex Updated"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "patient"  # role unchanged!
    assert data["name"] == "Alex Updated"

    patient_user = db.query(User).filter(User.name == "Alex Updated").first()
    assert patient_user.role == "patient"


# 18. Rejected professionals cannot use protected professional functionality
def test_18_rejected_professionals_cannot_use_functionality(client, admin_token):
    # 1. Register a doctor
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Dr. Rejected",
            "email": "dr_rejected@lifelink.org",
            "password": "DoctorPassword123!",
            "role": "doctor",
            "medicalLicenseNumber": "MCI-FAKE-000",
        },
    )
    assert reg_resp.status_code == 201
    doc_id = reg_resp.json()["user"]["id"]
    doc_token = reg_resp.json()["token"]

    # 2. Admin rejects the doctor
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    rej_resp = client.post(
        f"/api/v1/users/{doc_id}/reject",
        headers=admin_headers,
        json={"status": "rejected", "notes": "Medical license invalid"},
    )
    assert rej_resp.status_code == 200
    assert rej_resp.json()["verificationStatus"] == "rejected"
    assert rej_resp.json()["isVerified"] is False

    # 3. Doctor tries to create emergency -> rejected with 403 Forbidden
    doc_headers = {"Authorization": f"Bearer {doc_token}"}
    resp = client.post(
        "/api/v1/emergencies",
        headers=doc_headers,
        json={
            "type": "blood",
            "priority": "critical",
            "hospitalId": "city-hospital-001",
            "description": "Attempt by rejected doctor",
        },
    )
    assert resp.status_code == 403
    assert "rejected" in get_error_message(resp)



# 19. Unauthorized access to private records is prevented
def test_19_unauthorized_access_to_private_records_prevented(client, patient_token, donor_token):
    # Patient cannot view other users or admin users list
    headers = {"Authorization": f"Bearer {patient_token}"}
    resp = client.get("/api/v1/users", headers=headers)
    assert resp.status_code == 403

    # Patient cannot view pending verifications
    resp2 = client.get("/api/v1/users/pending-verification", headers=headers)
    assert resp2.status_code == 403

    # Donor cannot access patient private emergency endpoint
    donor_headers = {"Authorization": f"Bearer {donor_token}"}
    resp3 = client.get("/api/v1/emergencies/patient/me", headers=donor_headers)
    assert resp3.status_code == 403


# 20. Existing application functionality continues to pass
def test_20_existing_application_functionality_intact(client, doctor_token, ambulance_token, admin_token):
    # Doctor can list ambulances
    r1 = client.get("/api/v1/ambulances")
    assert r1.status_code == 200

    # Doctor can view hospitals
    r2 = client.get("/api/v1/hospitals")
    assert r2.status_code == 200

    # Admin can view platform users
    r3 = client.get("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert r3.status_code == 200
    assert len(r3.json()) >= 7
