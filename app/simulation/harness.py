import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db
from app.schemas.auth import UserProfileSchema
from app.simulation.sandbox_db import SandboxDatabase
from app.simulation.mock_notifications import mock_notification_provider
from app.simulation import scenarios


class SimulationHarness:
    """LifeLink Operational Simulation and Telemetry Verification Harness."""

    def __init__(self, db_path: Optional[str] = None):
        self.sandbox = SandboxDatabase(db_path=db_path)
        self.results: List[Dict[str, Any]] = []
        self.user = UserProfileSchema(
            id="usr-doc-01",
            name="Dr. Sim Physician",
            email="dr.sim@lifelink.org",
            role="doctor",
            roleTitle="Chief Emergency Officer",
            hospitalId="city-hospital-001",
            hospitalName="City General Hospital",
            isVerified=True,
        )

    def execute_all(self) -> Dict[str, Any]:
        """Executes all 15 operational simulation and telemetry verification scenarios."""
        start_time = time.time()
        self.sandbox.initialize_schema_with_alembic()
        self.sandbox.seed_fixtures()
        mock_notification_provider.clear()

        # Wire FastAPI TestClient with sandbox database
        def override_get_db():
            s = self.sandbox.get_session()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[get_db] = override_get_db
        test_client = TestClient(app)

        try:
            db = self.sandbox.get_session()

            # Scenarios 1-10
            s1 = scenarios.run_scenario_01_valid_emergency_creation(db, self.user)
            self.results.append(s1)

            s2 = scenarios.run_scenario_02_unknown_hospital_rejection(db, self.user)
            self.results.append(s2)

            s3 = scenarios.run_scenario_03_resolution_and_cancellation(db, self.user)
            self.results.append(s3)

            s4 = scenarios.run_scenario_04_invalid_transitions_and_idempotency(db, self.user)
            self.results.append(s4)

            s5 = scenarios.run_scenario_05_consent_denial_guard(db, self.user)
            self.results.append(s5)

            s6 = scenarios.run_scenario_06_synthetic_donor_guard(db, self.user)
            self.results.append(s6)

            s7 = scenarios.run_scenario_07_candidate_deduplication_and_filtering(db, self.user)
            self.results.append(s7)

            s8 = scenarios.run_scenario_08_interaction_lifecycle_states(db, self.user)
            self.results.append(s8)

            s9 = scenarios.run_scenario_09_completion_rule_enforcement(db, self.user)
            self.results.append(s9)

            s10 = scenarios.run_scenario_10_transaction_rollback_safety(db, self.user)
            self.results.append(s10)

            # Scenarios 11-12 (Concurrency)
            s11 = scenarios.run_scenario_11_concurrent_requests_same_emergency(
                self.sandbox.get_session, self.user, concurrency=5
            )
            self.results.append(s11)

            s12 = scenarios.run_scenario_12_concurrent_multiple_emergencies(
                self.sandbox.get_session, self.user, count=5
            )
            self.results.append(s12)

            # Scenarios 13-15 (WebSocket Telemetry)
            s13 = scenarios.run_scenario_13_websocket_event_delivery(test_client, db, self.user)
            self.results.append(s13)

            s14 = scenarios.run_scenario_14_websocket_reconnect(test_client)
            self.results.append(s14)

            s15 = scenarios.run_scenario_15_telemetry_ordering_and_consistency(test_client, db, self.user)
            self.results.append(s15)

            db.close()
        finally:
            app.dependency_overrides.clear()
            self.sandbox.teardown()

        total_duration_ms = round((time.time() - start_time) * 1000, 2)
        passed_count = sum(1 for r in self.results if r["status"] == "passed")
        failed_count = sum(1 for r in self.results if r["status"] != "passed")

        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sandbox_db_url": self.sandbox.db_url,
            "total_scenarios": len(self.results),
            "passed": passed_count,
            "failed": failed_count,
            "total_duration_ms": total_duration_ms,
            "notifications_dispatched": mock_notification_provider.count(),
            "scenarios": self.results,
        }
        return summary
