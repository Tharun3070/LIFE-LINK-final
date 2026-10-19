def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "lifelink-backend"


def test_readiness_check(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_system_status(client):
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert data["overallHealthy"] is True
    assert data["database"] == "operational"
    assert data["realtime"] == "operational"
    assert data["llm"] == "not_configured"
    assert data["rag"] == "not_configured"
    assert data["xgboost"] == "not_configured"
    assert data["geospatial"] == "not_configured"
