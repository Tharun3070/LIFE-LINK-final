def test_doctor_can_create_emergency(client, doctor_token):
    response = client.post(
        "/api/v1/emergencies",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={
            "type": "blood",
            "priority": "critical",
            "hospitalId": "city-hospital-001",
            "description": "Critical emergency for surgical trauma",
            "bloodGroup": "O-",
            "unitsRequired": 2,
        },
    )
    assert response.status_code == 200
    assert response.json()["type"] == "blood"


def test_donor_cannot_create_emergency(client, donor_token):
    response = client.post(
        "/api/v1/emergencies",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={
            "type": "blood",
            "priority": "critical",
            "hospitalId": "city-hospital-001",
            "description": "Unauthorized emergency creation attempt",
        },
    )
    assert response.status_code == 403


def test_patient_cannot_create_emergency(client, patient_token):
    response = client.post(
        "/api/v1/emergencies",
        headers={"Authorization": f"Bearer {patient_token}"},
        json={
            "type": "blood",
            "priority": "critical",
            "hospitalId": "city-hospital-001",
            "description": "Patient unauthorized creation attempt",
        },
    )
    assert response.status_code == 403


def test_admin_can_view_users(client, admin_token):
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert len(response.json()) >= 7


def test_doctor_cannot_view_admin_users(client, doctor_token):
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert response.status_code == 403


def test_patient_cannot_view_admin_users(client, patient_token):
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert response.status_code == 403


def test_donor_cannot_view_admin_users(client, donor_token):
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert response.status_code == 403


def test_coordinator_can_review_organ(client, coordinator_token):
    response = client.post(
        "/api/v1/organs/ORG-K-001/clinical-review",
        headers={"Authorization": f"Bearer {coordinator_token}"},
        json={"decision": "approved", "notes": "Authorized coordinator approval"},
    )
    assert response.status_code == 200


def test_patient_cannot_review_organ(client, patient_token):
    response = client.post(
        "/api/v1/organs/ORG-K-001/clinical-review",
        headers={"Authorization": f"Bearer {patient_token}"},
        json={"decision": "approved"},
    )
    assert response.status_code == 403
