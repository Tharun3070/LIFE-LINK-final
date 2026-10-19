def test_login_success(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "doctor@lifelink.demo", "password": "doctor123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["user"]["email"] == "doctor@lifelink.demo"
    assert data["user"]["role"] == "doctor"
    assert "view_command_center" in data["user"]["permissions"]


def test_login_invalid_password(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "doctor@lifelink.demo", "password": "wrongpassword"},
    )
    assert response.status_code == 401


def test_login_unknown_user(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "nonexistent@hospital.org", "password": "pass"},
    )
    assert response.status_code == 401


def test_auth_me(client, doctor_token):
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "doctor"
    assert data["name"] == "Dr. Arjun Rao"


def test_auth_me_unauthorized(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_auth_permissions(client, doctor_token):
    response = client.get(
        "/api/v1/auth/permissions",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "create_blood_emergency" in data["permissions"]


def test_login_missing_password(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "doctor@lifelink.demo"},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["code"] == "VALIDATION_ERROR"
    assert any("password" in err["loc"] for err in data.get("details", []))


def test_login_missing_identifier(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"password": "doctor123"},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["code"] == "VALIDATION_ERROR"
    assert any("identifier" in err["loc"] for err in data.get("details", []))


def test_auth_refresh(client):
    # Login to get refresh token
    login_res = client.post(
        "/api/v1/auth/login",
        json={"identifier": "doctor@lifelink.demo", "password": "doctor123"},
    )
    assert login_res.status_code == 200
    refresh_token = login_res.json()["refreshToken"]

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_auth_logout(client, doctor_token):
    response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Logged out successfully"

    # Verify that session is marked inactive and token is revoked
    me_res = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert me_res.status_code == 401


def test_demo_jwt_bypass_rejected(client):
    # Verify that demo_jwt_token_* format is strictly rejected and never accepted
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer demo_jwt_token_usr-doc-001_1720000000"},
    )
    assert response.status_code == 401


def test_password_verification_and_malformed_hashes():
    from app.core.security import verify_password, get_password_hash

    # 1. Valid password
    hashed = get_password_hash("securepass123")
    assert verify_password("securepass123", hashed) is True

    # 2. Invalid password
    assert verify_password("wrongpass", hashed) is False

    # 3. Malformed stored password (plaintext without bcrypt salt/header)
    assert verify_password("plainpass", "plainpass") is False
    assert verify_password("plainpass", "not_a_valid_bcrypt_hash") is False
    assert verify_password("plainpass", "$2b$invalid_short_hash") is False

    # 4. Empty passwords
    assert verify_password("", hashed) is False
    assert verify_password("securepass123", "") is False
    assert verify_password("", "") is False
