def test_list_emergencies(client, doctor_token):
    response = client.get("/api/v1/emergencies", headers={"Authorization": f"Bearer {doctor_token}"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3


def test_get_emergency_by_id(client, doctor_token):
    response = client.get("/api/v1/emergencies/BL-102", headers={"Authorization": f"Bearer {doctor_token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "BL-102"
    assert data["bloodGroup"] == "O-"


def test_get_emergency_not_found(client, doctor_token):
    response = client.get("/api/v1/emergencies/NONEXISTENT-999", headers={"Authorization": f"Bearer {doctor_token}"})
    assert response.status_code == 404


def test_resolve_emergency(client, doctor_token):
    response = client.post(
        "/api/v1/emergencies/BL-102/resolve",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "resolved"


def test_cancel_emergency(client, doctor_token):
    response = client.post(
        "/api/v1/emergencies/BL-103/cancel",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_get_kpis(client):
    response = client.get("/api/v1/dashboard/kpis")
    assert response.status_code == 200
    data = response.json()
    assert "activeEmergencies" in data
    assert "bloodRequests" in data


def test_get_activity_timeline(client):
    response = client.get("/api/v1/activity?emergencyId=BL-102")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_create_emergency_with_valid_hospital(client, doctor_token, db):
    from app.models.emergency import EmergencyEvent
    from app.models.audit import AuditLog

    res = client.post(
        "/api/v1/emergencies",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={
            "type": "blood",
            "priority": "critical",
            "hospitalId": "city-hospital-001",
            "description": "Urgent trauma blood need",
            "bloodGroup": "O-",
            "unitsRequired": 2,
        },
    )
    assert res.status_code == 200
    em_data = res.json()
    assert em_data["hospitalId"] == "city-hospital-001"
    assert em_data["hospitalName"] == "City General Hospital"

    # Verify timeline event was created
    evts = db.query(EmergencyEvent).filter(EmergencyEvent.emergency_id == em_data["id"]).all()
    assert len(evts) == 1
    assert "Emergency created: BLOOD (CRITICAL)" in evts[0].action

    # Verify audit log was created
    audits = db.query(AuditLog).filter(AuditLog.resource_id == em_data["id"]).all()
    assert len(audits) >= 1
    assert audits[0].status == "success"


def test_create_emergency_rejects_unknown_hospital(client, doctor_token, db):
    from app.models.emergency import Emergency, EmergencyEvent
    from app.models.audit import AuditLog

    initial_emerg_count = db.query(Emergency).count()

    res = client.post(
        "/api/v1/emergencies",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={
            "type": "blood",
            "priority": "critical",
            "hospitalId": "hosp-001",  # Unknown ID
            "description": "Attempt with unknown hospital",
            "bloodGroup": "O-",
            "unitsRequired": 1,
        },
    )
    assert res.status_code == 400
    assert "Hospital with ID 'hosp-001' not found" in res.json()["message"]

    # Verify no emergency was persisted
    assert db.query(Emergency).count() == initial_emerg_count

    # Verify failure audit log was recorded
    failed_audit = db.query(AuditLog).filter(
        AuditLog.status == "failed",
        AuditLog.resource_id == "hosp-001",
    ).first()
    assert failed_audit is not None
    assert "Unknown hospital ID" in failed_audit.action


def test_create_emergency_blood_requires_hospital(client, doctor_token):
    res = client.post(
        "/api/v1/emergencies",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={
            "type": "blood",
            "priority": "critical",
            "hospitalId": None,
            "description": "Blood emergency missing hospital",
            "bloodGroup": "O-",
            "unitsRequired": 1,
        },
    )
    assert res.status_code == 400
    assert "Hospital ID is required for blood emergencies" in res.json()["message"]


def test_create_emergency_ambulance_omitted_hospital_fallback(client, doctor_token, db):
    res = client.post(
        "/api/v1/emergencies",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={
            "type": "ambulance",
            "priority": "high",
            "hospitalId": None,
            "description": "General transit emergency without hospital specified",
            "origin": "Airport Road",
            "destination": "Trauma Center",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "ambulance"
    assert data["hospitalId"] == "city-hospital-001"
    assert data["hospitalName"] == "City General Hospital"


def test_resolve_emergency_emits_event_and_audit(client, doctor_token, db):
    from app.models.emergency import EmergencyEvent
    from app.models.audit import AuditLog

    # Resolve BL-102
    res = client.post(
        "/api/v1/emergencies/BL-102/resolve",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "resolved"
    assert res.json()["resolvedAt"] is not None

    # Verify timeline event was added
    res_event = db.query(EmergencyEvent).filter(
        EmergencyEvent.emergency_id == "BL-102",
        EmergencyEvent.action.like("%Emergency resolved%"),
    ).first()
    assert res_event is not None
    assert res_event.status == "success"

    # Verify audit log was recorded
    res_audit = db.query(AuditLog).filter(
        AuditLog.resource_id == "BL-102",
        AuditLog.action.like("%Resolved Blood Emergency SOS%"),
    ).first()
    assert res_audit is not None
    assert res_audit.status == "success"


def test_resolve_emergency_idempotent_retry(client, doctor_token, db):
    from app.models.emergency import EmergencyEvent
    from app.models.audit import AuditLog

    # First resolve
    client.post(
        "/api/v1/emergencies/BL-102/resolve",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    events_after_first = db.query(EmergencyEvent).filter(
        EmergencyEvent.emergency_id == "BL-102",
        EmergencyEvent.action.like("%Emergency resolved%"),
    ).count()

    # Second resolve (retry)
    res_retry = client.post(
        "/api/v1/emergencies/BL-102/resolve",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert res_retry.status_code == 200
    assert res_retry.json()["status"] == "resolved"

    events_after_second = db.query(EmergencyEvent).filter(
        EmergencyEvent.emergency_id == "BL-102",
        EmergencyEvent.action.like("%Emergency resolved%"),
    ).count()
    # Idempotent: no duplicate event created
    assert events_after_second == events_after_first


def test_resolve_emergency_rejects_cancelled(client, doctor_token):
    # BL-103 is cancelled in first cancel test, or let's cancel it first
    client.post(
        "/api/v1/emergencies/BL-103/cancel",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    # Attempting to resolve cancelled emergency must fail with 400
    res = client.post(
        "/api/v1/emergencies/BL-103/resolve",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert res.status_code == 400
    assert "already been cancelled" in res.json()["message"]


def test_cancel_emergency_emits_event_and_audit(client, doctor_token, db):
    from app.models.emergency import EmergencyEvent
    from app.models.audit import AuditLog

    res = client.post(
        "/api/v1/emergencies/BL-103/cancel",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"

    # Verify event
    cancel_event = db.query(EmergencyEvent).filter(
        EmergencyEvent.emergency_id == "BL-103",
        EmergencyEvent.action.like("%Emergency cancelled%"),
    ).first()
    assert cancel_event is not None

    # Verify audit
    cancel_audit = db.query(AuditLog).filter(
        AuditLog.resource_id == "BL-103",
        AuditLog.action.like("%Cancelled Blood Emergency SOS%"),
    ).first()
    assert cancel_audit is not None


def test_cancel_emergency_idempotent_retry(client, doctor_token, db):
    from app.models.emergency import EmergencyEvent

    client.post(
        "/api/v1/emergencies/BL-103/cancel",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    count1 = db.query(EmergencyEvent).filter(
        EmergencyEvent.emergency_id == "BL-103",
        EmergencyEvent.action.like("%Emergency cancelled%"),
    ).count()

    res_retry = client.post(
        "/api/v1/emergencies/BL-103/cancel",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert res_retry.status_code == 200
    count2 = db.query(EmergencyEvent).filter(
        EmergencyEvent.emergency_id == "BL-103",
        EmergencyEvent.action.like("%Emergency cancelled%"),
    ).count()
    assert count2 == count1


def test_cancel_emergency_rejects_resolved(client, doctor_token):
    # Resolve BL-102 first
    client.post(
        "/api/v1/emergencies/BL-102/resolve",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    # Attempting to cancel resolved emergency must fail with 400
    res = client.post(
        "/api/v1/emergencies/BL-102/cancel",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert res.status_code == 400
    assert "already been resolved" in res.json()["message"]


def test_resolve_cancel_unauthorized_for_donor_patient(client, donor_token, patient_token):
    # Donor cannot resolve
    res1 = client.post(
        "/api/v1/emergencies/BL-102/resolve",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert res1.status_code == 403

    # Donor cannot cancel
    res2 = client.post(
        "/api/v1/emergencies/BL-102/cancel",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert res2.status_code == 403

    # Patient cannot resolve
    res3 = client.post(
        "/api/v1/emergencies/BL-102/resolve",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert res3.status_code == 403

    # Patient cannot cancel
    res4 = client.post(
        "/api/v1/emergencies/BL-102/cancel",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert res4.status_code == 403


def test_resolve_emergency_broadcasts_websocket_event(client, doctor_token):
    """Verifies that resolving an emergency broadcasts an emergency.updated event via WebSocket."""
    with client.websocket_connect(f"/ws?token={doctor_token}") as ws:
        welcome = ws.receive_json()
        assert welcome["type"] == "connection.established"

        res = client.post(
            "/api/v1/emergencies/BL-102/resolve",
            headers={"Authorization": f"Bearer {doctor_token}"},
        )
        assert res.status_code == 200

        event = ws.receive_json()
        assert event["type"] == "emergency.updated"
        assert event["payload"]["emergencyId"] == "BL-102"
        assert event["payload"]["status"] == "resolved"
        assert event["payload"]["action"] == "resolved"


def test_cancel_emergency_broadcasts_websocket_event(client, doctor_token):
    """Verifies that cancelling an emergency broadcasts an emergency.updated event via WebSocket."""
    with client.websocket_connect(f"/ws?token={doctor_token}") as ws:
        welcome = ws.receive_json()
        assert welcome["type"] == "connection.established"

        res = client.post(
            "/api/v1/emergencies/BL-103/cancel",
            headers={"Authorization": f"Bearer {doctor_token}"},
        )
        assert res.status_code == 200

        event = ws.receive_json()
        assert event["type"] == "emergency.updated"
        assert event["payload"]["emergencyId"] == "BL-103"
        assert event["payload"]["status"] == "cancelled"
        assert event["payload"]["action"] == "cancelled"


def test_update_emergency_broadcasts_websocket_event(client, doctor_token):
    """Verifies that updating an emergency broadcasts an emergency.updated event with latest attributes."""
    with client.websocket_connect(f"/ws?token={doctor_token}") as ws:
        welcome = ws.receive_json()
        assert welcome["type"] == "connection.established"

        res = client.patch(
            "/api/v1/emergencies/BL-102",
            headers={"Authorization": f"Bearer {doctor_token}"},
            json={"priority": "high", "eta": 18},
        )
        assert res.status_code == 200

        event = ws.receive_json()
        assert event["type"] == "emergency.updated"
        assert event["payload"]["emergencyId"] == "BL-102"
        assert event["payload"]["priority"] == "high"
        assert event["payload"]["eta"] == 18
        assert event["payload"]["action"] == "updated"


def test_websocket_reconnect_authoritative_refresh_sequence(client, doctor_token):
    """Verifies that upon reconnecting, a client receives connection.established and queries fresh authoritative state."""
    # 1. First connection
    with client.websocket_connect(f"/ws?token={doctor_token}") as ws1:
        w1 = ws1.receive_json()
        assert w1["type"] == "connection.established"

    # 2. Reconnect: gateway emits fresh connection.established
    with client.websocket_connect(f"/ws?token={doctor_token}") as ws2:
        w2 = ws2.receive_json()
        assert w2["type"] == "connection.established"

        # Client triggers authoritative refresh
        em_res = client.get("/api/v1/emergencies", headers={"Authorization": f"Bearer {doctor_token}"})
        kpi_res = client.get("/api/v1/dashboard/kpis")

        assert em_res.status_code == 200
        assert kpi_res.status_code == 200
        assert isinstance(em_res.json(), list)
        assert "activeEmergencies" in kpi_res.json()


