def test_create_blood_request(client, doctor_token):
    response = client.post(
        "/api/v1/blood/requests",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={
            "bloodGroup": "O-",
            "unitsRequired": 3,
            "priority": "critical",
            "hospitalId": "city-hospital-001",
            "notes": "Emergency surgery in OR 2",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "blood"
    assert data["bloodGroup"] == "O-"
    assert data["unitsRequired"] == 3


def test_get_ranked_donors(client):
    response = client.get("/api/v1/blood/donors/ranked?emergencyId=BL-102")
    assert response.status_code == 200
    data = response.json()
    assert "donors" in data
    assert "searchConfig" in data
    assert "aiRecommendation" in data
    assert len(data["donors"]) >= 1
    assert data["searchConfig"]["initialRadiusKm"] == 2.0


def test_contact_donor(client, doctor_token):
    # D-101 has verified emergency communication consent granted
    response = client.post(
        "/api/v1/blood/donors/D-101/contact",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "contacted"


def test_contact_donor_consent_denied(client, doctor_token, db):
    from app.models.consent import Consent
    from app.models.audit import AuditLog

    # Revoke emergency communication consent for donor D-101's user
    consent = db.query(Consent).filter(Consent.user_id == "usr-dnr-005").first()
    assert consent is not None
    consent.emergency_communication = False
    db.commit()

    response = client.post(
        "/api/v1/blood/donors/D-101/contact",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102"},
    )
    assert response.status_code == 403
    assert "not granted emergency communication consent" in response.json()["message"]

    # Verify decision is recorded in audit log
    denied_audit = db.query(AuditLog).filter(
        AuditLog.resource_id == "D-101",
        AuditLog.status == "failed",
    ).first()
    assert denied_audit is not None
    assert "Emergency communication consent not granted" in denied_audit.action


def test_contact_donor_not_found(client, doctor_token):
    response = client.post(
        "/api/v1/blood/donors/D-NONEXISTENT/contact",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"emergencyId": "BL-102"},
    )
    assert response.status_code == 404


def test_donor_respond(client, donor_token):
    response = client.post(
        "/api/v1/blood/donors/D-101/response",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"status": "accepted", "shareLocation": True},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["locationConsentGranted"] is True


def test_get_donor_me(client, donor_token):
    response = client.get(
        "/api/v1/donors/me",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["bloodGroup"] == "O-"


def test_list_donors_filtering_and_pagination(client, donor_token):
    response = client.get(
        "/api/v1/donors?blood_group=O-&status=available&skip=0&limit=5",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert response.status_code == 200
    donors = response.json()
    assert isinstance(donors, list)
    for d in donors:
        assert d["bloodGroup"] == "O-"
        assert d["status"] == "available"


def test_set_donor_availability_persists(client, donor_token, db):
    from app.models.donor import Donor

    # Set availability to unavailable
    response = client.post(
        "/api/v1/donors/me/availability",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"status": "unavailable"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"

    # Verify directly in DB
    donor = db.query(Donor).filter(Donor.user_id == "usr-dnr-005").first()
    assert donor is not None
    assert donor.status == "unavailable"

    # Set back to available
    resp_avail = client.post(
        "/api/v1/donors/me/availability",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"status": "available"},
    )
    assert resp_avail.status_code == 200
    db.refresh(donor)
    assert donor.status == "available"

    # Test invalid status
    resp_invalid = client.post(
        "/api/v1/donors/me/availability",
        headers={"Authorization": f"Bearer {donor_token}"},
        json={"status": "invalid_status"},
    )
    assert resp_invalid.status_code in [400, 422]


def test_emergencies_filtering(client, doctor_token):
    response = client.get(
        "/api/v1/emergencies?type=blood",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert response.status_code == 200
    emergencies = response.json()
    assert isinstance(emergencies, list)
    for e in emergencies:
        assert e["type"] == "blood"


def test_hospitals_filtering(client):
    response = client.get("/api/v1/hospitals?city=Bengaluru&blood_bank_available=true")
    assert response.status_code == 200
    hospitals = response.json()
    assert isinstance(hospitals, list)
    for h in hospitals:
        assert "Bengaluru" in h["city"]
        assert h["bloodBankAvailable"] is True
