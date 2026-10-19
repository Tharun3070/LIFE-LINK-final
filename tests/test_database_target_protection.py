"""Tests for database target verification, protection guards, and mock notification isolation.
Verifies that write-oriented testing cannot run against canonical/legacy databases,
and that notification pathways are strictly isolated to the mock provider.
"""
import pytest
from app.core.config import Settings
from app.simulation.mock_notifications import (
    MockNotificationProvider,
    LiveCarrierInvocationProhibitedError,
    mock_notification_provider,
)
from app.simulation.sandbox_db import assert_sandbox_isolated, CanonicalDatabaseProtectionViolation


def test_sanitized_database_info_in_memory():
    """Confirms in-memory SQLite is correctly recognized as sandbox and safe."""
    s = Settings(DATABASE_URL="sqlite:///:memory:")
    info = s.get_sanitized_database_info()
    assert info["dialect"] == "sqlite"
    assert info["resolved_target"] == ":memory:"
    assert info["is_canonical"] is False
    assert info["is_legacy_root"] is False
    assert info["is_sandbox"] is True
    # Guard must pass
    s.assert_isolated_target_for_write_testing()


def test_sanitized_database_info_sandbox_file():
    """Confirms named sandbox databases are recognized as safe."""
    s = Settings(DATABASE_URL="sqlite:///./lifelink_demo_sandbox.db")
    info = s.get_sanitized_database_info()
    assert info["dialect"] == "sqlite"
    assert "sandbox" in info["resolved_target"]
    assert info["is_canonical"] is False
    assert info["is_legacy_root"] is False
    assert info["is_sandbox"] is True
    # Guard must pass
    s.assert_isolated_target_for_write_testing()


def test_protection_guard_blocks_canonical_database():
    """Confirms that if DATABASE_URL points to canonical lifelink.db, the write guard strictly raises RuntimeError."""
    import os
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    canonical_path = os.path.normcase(os.path.abspath(os.path.join(backend_dir, "lifelink.db"))).replace("\\", "/")
    
    s = Settings(DATABASE_URL=f"sqlite:///{canonical_path}")
    info = s.get_sanitized_database_info()
    assert info["is_canonical"] is True
    assert info["is_sandbox"] is False

    with pytest.raises(RuntimeError) as exc_info:
        s.assert_isolated_target_for_write_testing()
    assert "PROTECTED DATABASE GUARD" in str(exc_info.value)
    assert "canonical" in str(exc_info.value)


def test_protection_guard_blocks_root_legacy_database():
    """Confirms that if DATABASE_URL points to root legacy lifelink.db, the write guard strictly raises RuntimeError."""
    import os
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    root_dir = os.path.abspath(os.path.join(backend_dir, ".."))
    root_path = os.path.normcase(os.path.abspath(os.path.join(root_dir, "lifelink.db"))).replace("\\", "/")

    s = Settings(DATABASE_URL=f"sqlite:///{root_path}")
    info = s.get_sanitized_database_info()
    assert info["is_legacy_root"] is True
    assert info["is_sandbox"] is False

    with pytest.raises(RuntimeError) as exc_info:
        s.assert_isolated_target_for_write_testing()
    assert "PROTECTED DATABASE GUARD" in str(exc_info.value)


def test_sandbox_isolated_helper_blocks_canonical_paths():
    """Confirms that assert_sandbox_isolated raises CanonicalDatabaseProtectionViolation."""
    import os
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    canonical_path = os.path.normcase(os.path.abspath(os.path.join(backend_dir, "lifelink.db"))).replace("\\", "/")

    with pytest.raises(CanonicalDatabaseProtectionViolation):
        assert_sandbox_isolated(f"sqlite:///{canonical_path}")


def test_mock_notification_isolation():
    """Verifies that mock notification provider records dispatches without external network calls."""
    provider = MockNotificationProvider()
    provider.clear()
    assert provider.count() == 0

    record = provider.dispatch(
        recipient="Donor #10 (O-)",
        message="Urgent blood request test",
        channel="sms",
        metadata={"emergency_id": "emg-test-01"},
    )
    assert record.status == "mock_delivered"
    assert record.recipient == "Donor #10 (O-)"
    assert provider.count() == 1
    assert len(provider.get_records()) == 1
    provider.clear()


def test_carrier_isolation_raises_on_live_credentials(monkeypatch):
    """Verifies that if TWILIO credentials exist and MOCK_NOTIFICATIONS_ONLY is False, isolation error is raised."""
    provider = MockNotificationProvider()
    from app.core.config import settings
    monkeypatch.setattr(settings, "MOCK_NOTIFICATIONS_ONLY", False)
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "AC_test_simulated_live_credential")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "auth_token_simulated")

    with pytest.raises(LiveCarrierInvocationProhibitedError) as exc_info:
        provider.assert_carrier_isolation()
    assert "CRITICAL CARRIER ISOLATION FAILURE" in str(exc_info.value)
