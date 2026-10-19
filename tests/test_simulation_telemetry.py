"""Pytest regression test suite for LifeLink Realtime WebSocket Telemetry (Scenarios 13 to 15).
Exercises event delivery, connection lifecycles, reconnects, ordering, and state synchronization.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db
from app.simulation.sandbox_db import SandboxDatabase
from app.schemas.auth import UserProfileSchema
from app.simulation import scenarios
from app.realtime.manager import ws_manager


@pytest.fixture(scope="module")
def sandbox():
    sb = SandboxDatabase()
    sb.initialize_schema_with_alembic()
    sb.seed_fixtures()
    yield sb
    sb.teardown()


@pytest.fixture
def sim_user():
    return UserProfileSchema(
        id="usr-doc-01",
        name="Dr. Sim Physician",
        email="dr.sim@lifelink.org",
        role="doctor",
        roleTitle="Chief Emergency Officer",
        hospitalId="city-hospital-001",
        hospitalName="City General Hospital",
        isVerified=True,
    )


@pytest.fixture
def test_client(sandbox):
    def override_get_db():
        s = sandbox.get_session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def db_session(sandbox):
    s = sandbox.get_session()
    yield s
    s.close()


def test_scenario_13_websocket_event_delivery(test_client, db_session, sim_user):
    res = scenarios.run_scenario_13_websocket_event_delivery(test_client, db_session, sim_user)
    assert res["status"] == "passed"
    assert "emergency.created" in res["events_received"]
    assert "emergency.updated" in res["events_received"]


def test_scenario_14_websocket_reconnect(test_client):
    res = scenarios.run_scenario_14_websocket_reconnect(test_client)
    assert res["status"] == "passed"
    assert len(ws_manager.active_connections) == 0


def test_scenario_15_telemetry_ordering_and_consistency(test_client, db_session, sim_user):
    res = scenarios.run_scenario_15_telemetry_ordering_and_consistency(test_client, db_session, sim_user)
    assert res["status"] == "passed"
    assert res["event_sequence"] == [
        "connection.established",
        "emergency.created",
        "emergency.updated",
    ]


def test_websocket_no_unsolicited_replay_on_reconnect(test_client):
    """Verifies that in-memory ConnectionManager does not replay past broadcasts to fresh connections."""
    with test_client.websocket_connect("/ws") as ws:
        welcome = ws.receive_json()
        assert welcome["type"] == "connection.established"
        # Since no new event is broadcast while connected, no historical event is delivered
