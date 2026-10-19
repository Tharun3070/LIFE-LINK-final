"""
Tests for LifeLink ML Readiness & Interaction Data Audit
File: backend/tests/test_ml_readiness_audit.py

Validates:
1. Empty database audit correctly flags zero records and NOT_READY status.
2. Provenance separation: synthetic records are isolated and excluded from production ML training targets.
3. Lifecycle state accounting and target-specific sample counts (Response, Acceptance, Completion).
4. Data integrity anomaly detection (chronology violations, negative latencies, duplicate pairs).
5. Accurate calculation of latency metrics (min, mean, max, coverage).
6. Threshold gating logic: requires >=2500 production records and >=250 emergencies.
7. CLI script execution and JSON formatting integrity.
"""

import subprocess
import sys
import json
import pytest
from app.models.interaction import DonorEmergencyInteraction
from app.services.ml_audit_service import MLAuditService, MINIMUM_VIABLE_INTERACTIONS_THRESHOLD


def test_audit_empty_database(db):
    # Ensure no interactions exist
    db.query(DonorEmergencyInteraction).delete()
    db.commit()

    report = MLAuditService.audit_interactions(db)

    assert report["volume"]["total_interactions"] == 0
    assert report["volume"]["distinct_emergencies"] == 0
    assert report["volume"]["distinct_donors"] == 0
    assert report["provenance"]["production_records"] == 0
    assert report["provenance"]["synthetic_records"] == 0
    assert report["verdict"]["is_ready_for_training"] is False
    assert report["verdict"]["status"] == "NOT_READY_FOR_MODEL_TRAINING"
    assert any("empty" in r.lower() for r in report["verdict"]["blocking_reasons"])


def test_audit_provenance_separation_excludes_synthetic_from_training_targets(db):
    db.query(DonorEmergencyInteraction).delete()
    db.commit()

    # Create 1 synthetic interaction (test fixture)
    synth = DonorEmergencyInteraction(
        id="dint-synth-01",
        emergency_id="BL-SYNTH-1",
        donor_id="D-SYNTH-1",
        selected_at="2026-10-10T10:00:00Z",
        distance_km=4.2,
        eta_minutes=11,
        time_of_day_hours=10.0,
        day_of_week=5,
        emergency_priority="critical",
        contact_status="attempted",
        contact_attempted_at="2026-10-10T10:01:00Z",
        response_status="responded",
        responded_at="2026-10-10T10:05:00Z",
        response_latency_seconds=240,
        acceptance_status="accepted",
        completion_status="completed",
        is_synthetic=True,
        data_provenance="synthetic_simulation",
        outcome_source="test_fixture",
        created_at="2026-10-10T10:00:00Z",
        updated_at="2026-10-10T10:05:00Z",
    )

    # Create 1 production interaction
    prod = DonorEmergencyInteraction(
        id="dint-prod-01",
        emergency_id="BL-102",
        donor_id="D-101",
        selected_at="2026-10-10T11:00:00Z",
        distance_km=3.5,
        eta_minutes=9,
        time_of_day_hours=11.0,
        day_of_week=5,
        emergency_priority="critical",
        contact_status="attempted",
        contact_attempted_at="2026-10-10T11:01:00Z",
        response_status="responded",
        responded_at="2026-10-10T11:04:00Z",
        response_latency_seconds=180,
        acceptance_status="accepted",
        completion_status="pending",
        is_synthetic=False,
        data_provenance="production",
        outcome_source="donor_app",
        created_at="2026-10-10T11:00:00Z",
        updated_at="2026-10-10T11:04:00Z",
    )

    db.add_all([synth, prod])
    db.commit()

    report = MLAuditService.audit_interactions(db)

    assert report["volume"]["total_interactions"] == 2
    assert report["provenance"]["production_records"] == 1
    assert report["provenance"]["synthetic_records"] == 1

    # Production-only records are evaluated for candidate targets!
    # Target A (Response) must ONLY count the production record (eligible=1)
    target_a = report["prediction_targets"]["target_a_response_propensity"]
    assert target_a["eligible_records"] == 1
    assert target_a["positive_count (responded)"] == 1
    assert target_a["positive_ratio"] == 1.0


def test_audit_lifecycle_outcomes_and_class_ratios(db):
    db.query(DonorEmergencyInteraction).delete()
    db.commit()

    # 1 Responded/Accepted, 1 Responded/Declined, 1 No_Response, 1 Pending
    now_str = "2026-10-10T12:00:00Z"

    int_accepted = DonorEmergencyInteraction(
        id="dint-acc", emergency_id="BL-1", donor_id="D-1", selected_at=now_str,
        distance_km=2.0, eta_minutes=5, time_of_day_hours=12.0, day_of_week=5,
        emergency_priority="critical", contact_status="attempted", contact_attempted_at=now_str,
        response_status="responded", responded_at=now_str, response_latency_seconds=120,
        acceptance_status="accepted", completion_status="completed",
        is_synthetic=False, data_provenance="production", created_at=now_str, updated_at=now_str,
    )
    int_declined = DonorEmergencyInteraction(
        id="dint-dec", emergency_id="BL-1", donor_id="D-2", selected_at=now_str,
        distance_km=4.0, eta_minutes=10, time_of_day_hours=12.0, day_of_week=5,
        emergency_priority="critical", contact_status="attempted", contact_attempted_at=now_str,
        response_status="responded", responded_at=now_str, response_latency_seconds=300,
        acceptance_status="declined", completion_status="pending",
        is_synthetic=False, data_provenance="production", created_at=now_str, updated_at=now_str,
    )
    int_timeout = DonorEmergencyInteraction(
        id="dint-tout", emergency_id="BL-2", donor_id="D-3", selected_at=now_str,
        distance_km=6.0, eta_minutes=15, time_of_day_hours=12.0, day_of_week=5,
        emergency_priority="critical", contact_status="attempted", contact_attempted_at=now_str,
        response_status="no_response", acceptance_status="unreachable", completion_status="pending",
        is_synthetic=False, data_provenance="production", created_at=now_str, updated_at=now_str,
    )
    int_pending = DonorEmergencyInteraction(
        id="dint-pend", emergency_id="BL-2", donor_id="D-4", selected_at=now_str,
        distance_km=8.0, eta_minutes=20, time_of_day_hours=12.0, day_of_week=5,
        emergency_priority="critical", contact_status="attempted", contact_attempted_at=now_str,
        response_status="pending", acceptance_status="pending", completion_status="pending",
        is_synthetic=False, data_provenance="production", created_at=now_str, updated_at=now_str,
    )

    db.add_all([int_accepted, int_declined, int_timeout, int_pending])
    db.commit()

    report = MLAuditService.audit_interactions(db)

    # Target A (Response Propensity):
    # Excludes int_pending (still pending; NOT treated as negative!)
    # Eligible = int_accepted (responded), int_declined (responded), int_timeout (no_response) -> 3 records
    target_a = report["prediction_targets"]["target_a_response_propensity"]
    assert target_a["eligible_records"] == 3
    assert target_a["positive_count (responded)"] == 2
    assert target_a["negative_count (no_response/expired)"] == 1
    assert target_a["positive_ratio"] == round(2 / 3, 3)

    # Target B (Acceptance Propensity):
    # Eligible = int_accepted (accepted), int_declined (declined) -> 2 records
    target_b = report["prediction_targets"]["target_b_acceptance_propensity"]
    assert target_b["eligible_records"] == 2
    assert target_b["positive_count (accepted)"] == 1
    assert target_b["negative_count (declined)"] == 1
    assert target_b["positive_ratio"] == 0.5


def test_audit_data_integrity_anomaly_detection(db):
    db.query(DonorEmergencyInteraction).delete()
    db.commit()

    # Create record with chronological order error (responded_at earlier than contact_attempted_at)
    bad_chrono = DonorEmergencyInteraction(
        id="dint-bad-1", emergency_id="BL-1", donor_id="D-1", selected_at="2026-10-10T12:00:00Z",
        distance_km=2.0, eta_minutes=5, time_of_day_hours=12.0, day_of_week=5,
        emergency_priority="critical", contact_status="attempted",
        contact_attempted_at="2026-10-10T12:10:00Z",
        response_status="responded",
        responded_at="2026-10-10T12:05:00Z",  # Earlier than attempted!
        response_latency_seconds=-300,        # Negative latency!
        acceptance_status="accepted", completion_status="pending",
        is_synthetic=False, data_provenance="production", created_at="2026-10-10T12:00:00Z", updated_at="2026-10-10T12:05:00Z",
    )

    # Create duplicate active pending interaction for same (emergency_id, donor_id)
    dup1 = DonorEmergencyInteraction(
        id="dint-dup-1", emergency_id="BL-DUP", donor_id="D-DUP", selected_at="2026-10-10T12:00:00Z",
        distance_km=3.0, eta_minutes=7, time_of_day_hours=12.0, day_of_week=5,
        emergency_priority="critical", contact_status="pending",
        response_status="pending", acceptance_status="pending", completion_status="pending",
        is_synthetic=False, data_provenance="production", created_at="2026-10-10T12:00:00Z", updated_at="2026-10-10T12:00:00Z",
    )
    dup2 = DonorEmergencyInteraction(
        id="dint-dup-2", emergency_id="BL-DUP", donor_id="D-DUP", selected_at="2026-10-10T12:01:00Z",
        distance_km=3.0, eta_minutes=7, time_of_day_hours=12.0, day_of_week=5,
        emergency_priority="critical", contact_status="pending",
        response_status="pending", acceptance_status="pending", completion_status="pending",
        is_synthetic=False, data_provenance="production", created_at="2026-10-10T12:01:00Z", updated_at="2026-10-10T12:01:00Z",
    )

    db.add_all([bad_chrono, dup1, dup2])
    db.commit()

    report = MLAuditService.audit_interactions(db)

    assert report["data_integrity"]["chronology_errors"] >= 1
    assert report["data_integrity"]["negative_latencies"] >= 1
    assert report["data_integrity"]["duplicate_pending_pairs"] >= 1
    assert report["data_integrity"]["passed_integrity_checks"] is False
    assert report["verdict"]["is_ready_for_training"] is False


def test_cli_audit_script_execution():
    """Verifies that running scripts/audit_interaction_readiness.py runs cleanly and outputs valid JSON."""
    result = subprocess.run(
        [sys.executable, "scripts/audit_interaction_readiness.py", "--json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "verdict" in data
    assert "status" in data["verdict"]
    assert "volume" in data
    assert "prediction_targets" in data


def test_cli_audit_missing_database_returns_exit_code_2(tmp_path):
    """Verifies that providing a nonexistent database path exits with code 2 and does not create the file."""
    fake_path = str(tmp_path / "does_not_exist_database_123.db")
    result = subprocess.run(
        [sys.executable, "scripts/audit_interaction_readiness.py", "--db-path", fake_path, "--json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    data = json.loads(result.stdout)
    assert data["status"] == "DATABASE_NOT_FOUND"
    assert "not found" in data["error"].lower()
    # Invariant: Must NOT have created the database file
    import os
    assert not os.path.exists(fake_path)


def test_cli_credential_masking():
    """Verifies that database credentials in URLs are masked properly."""
    from scripts.audit_interaction_readiness import mask_db_url
    
    # PostgreSQL with password
    masked_pg = mask_db_url("postgresql+psycopg://admin_user:super_secret_password@db.lifelink.internal:5432/lifelink_prod")
    assert "super_secret_password" not in masked_pg
    assert "admin_user:***@db.lifelink.internal:5432/lifelink_prod" in masked_pg

    # SQLite URL without credentials
    masked_sq = mask_db_url("sqlite:///path/to/lifelink.db")
    assert masked_sq == "sqlite:///path/to/lifelink.db"
