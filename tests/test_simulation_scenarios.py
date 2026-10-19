"""Pytest regression test suite for LifeLink Operational Simulation Scenarios 1 to 12.
Exercises isolated sandbox database, state machines, concurrency, rollback, and guards.
"""
import pytest
from app.simulation.sandbox_db import SandboxDatabase
from app.schemas.auth import UserProfileSchema
from app.simulation import scenarios
from app.simulation.mock_notifications import mock_notification_provider


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
def db_session(sandbox):
    s = sandbox.get_session()
    yield s
    s.close()


def test_scenario_01_valid_emergency_creation(db_session, sim_user):
    res = scenarios.run_scenario_01_valid_emergency_creation(db_session, sim_user)
    assert res["status"] == "passed"
    assert "emergency_id" in res


def test_scenario_02_unknown_hospital_rejection(db_session, sim_user):
    res = scenarios.run_scenario_02_unknown_hospital_rejection(db_session, sim_user)
    assert res["status"] == "passed"


def test_scenario_03_resolution_and_cancellation(db_session, sim_user):
    res = scenarios.run_scenario_03_resolution_and_cancellation(db_session, sim_user)
    assert res["status"] == "passed"


def test_scenario_04_invalid_transitions_and_idempotency(db_session, sim_user):
    res = scenarios.run_scenario_04_invalid_transitions_and_idempotency(db_session, sim_user)
    assert res["status"] == "passed"


def test_scenario_05_consent_denial_guard(db_session, sim_user):
    res = scenarios.run_scenario_05_consent_denial_guard(db_session, sim_user)
    assert res["status"] == "passed"
    assert mock_notification_provider.count() == 0


def test_scenario_06_synthetic_donor_guard(db_session, sim_user):
    res = scenarios.run_scenario_06_synthetic_donor_guard(db_session, sim_user)
    assert res["status"] == "passed"
    assert mock_notification_provider.count() == 0


def test_scenario_07_candidate_deduplication_and_filtering(db_session, sim_user):
    res = scenarios.run_scenario_07_candidate_deduplication_and_filtering(db_session, sim_user)
    assert res["status"] == "passed"


def test_scenario_08_interaction_lifecycle_states(db_session, sim_user):
    res = scenarios.run_scenario_08_interaction_lifecycle_states(db_session, sim_user)
    assert res["status"] == "passed"


def test_scenario_09_completion_rule_enforcement(db_session, sim_user):
    res = scenarios.run_scenario_09_completion_rule_enforcement(db_session, sim_user)
    assert res["status"] == "passed"


def test_scenario_10_transaction_rollback_safety(db_session, sim_user):
    res = scenarios.run_scenario_10_transaction_rollback_safety(db_session, sim_user)
    assert res["status"] == "passed"


def test_scenario_11_concurrent_requests_same_emergency(sandbox, sim_user):
    res = scenarios.run_scenario_11_concurrent_requests_same_emergency(sandbox.get_session, sim_user, concurrency=5)
    assert res["status"] == "passed"


def test_scenario_12_concurrent_multiple_emergencies(sandbox, sim_user):
    res = scenarios.run_scenario_12_concurrent_multiple_emergencies(sandbox.get_session, sim_user, count=5)
    assert res["status"] == "passed"
