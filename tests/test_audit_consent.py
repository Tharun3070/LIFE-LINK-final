def test_list_audit_logs(client, doctor_token):
    response = client.get(
        "/api/v1/audit",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_get_audit_log_by_id(client, doctor_token):
    response = client.get(
        "/api/v1/audit/audit-001",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "audit-001"
    assert data["actor"] == "Dr. Sarah Patel"


def test_audit_logs_unauthorized(client, donor_token):
    response = client.get(
        "/api/v1/audit",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert response.status_code == 403


def test_get_and_update_consent(client, donor_token):
    # Get consent
    get_res = client.get(
        "/api/v1/consent",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert get_res.status_code == 200
    assert get_res.json()["liveLocation"] is True

    # Update consent
    patch_res = client.patch(
        "/api/v1/consent",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"liveLocation": False},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["liveLocation"] is False


def test_list_hospitals(client):
    response = client.get("/api/v1/hospitals")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 4
    assert any(h["name"] == "City General Hospital" for h in data)


def test_get_hospital_by_id(client):
    response = client.get("/api/v1/hospitals/city-hospital-001")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "city-hospital-001"
    assert data["name"] == "City General Hospital"


def test_get_hospital_inventory(client):
    response = client.get("/api/v1/hospitals/city-hospital-001/inventory")
    assert response.status_code == 200
    data = response.json()
    assert "bloodInventory" in data
    assert "emergencyBaysTotal" in data


def test_get_hospital_emergencies(client):
    response = client.get("/api/v1/hospitals/city-hospital-001/emergencies")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(e["hospitalId"] == "city-hospital-001" for e in data)
