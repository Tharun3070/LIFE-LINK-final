import os
import tempfile
import uuid
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from alembic.config import Config
from alembic import command

from app.models.hospital import Hospital
from app.models.user import User
from app.models.consent import Consent
from app.models.donor import Donor
from app.models.ambulance import Ambulance
from app.core.security import get_password_hash


class CanonicalDatabaseProtectionViolation(RuntimeError):
    """Raised when any simulation process attempts to access or mutate a canonical database."""
    pass


def get_canonical_db_paths() -> list[str]:
    """Resolves absolute canonical paths for both backend/lifelink.db and root lifelink.db."""
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    root_dir = os.path.abspath(os.path.join(backend_dir, ".."))
    return [
        os.path.normcase(os.path.abspath(os.path.join(backend_dir, "lifelink.db"))),
        os.path.normcase(os.path.abspath(os.path.join(root_dir, "lifelink.db"))),
    ]


def assert_sandbox_isolated(db_url: str) -> None:
    """Fails safely if the resolved database path points to either canonical database."""
    canonical_paths = get_canonical_db_paths()

    # Extract SQLite path if applicable
    if "sqlite:///" in db_url:
        sqlite_file = db_url.replace("sqlite:///", "").replace("/", os.sep)
        resolved_target = os.path.normcase(os.path.abspath(sqlite_file))
        for canonical in canonical_paths:
            if resolved_target == canonical:
                raise CanonicalDatabaseProtectionViolation(
                    f"CRITICAL SAFETY VIOLATION: Database URL '{db_url}' resolves to canonical database '{canonical}'! "
                    "Simulation is strictly prohibited from executing against canonical production/development databases."
                )


class SandboxDatabase:
    """Manages the lifecycle of an isolated SQLite sandbox database with Alembic migrations applied."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            self._temp_dir = tempfile.mkdtemp(prefix="lifelink_sandbox_")
            self.db_path = os.path.join(self._temp_dir, f"sandbox_sim_{uuid.uuid4().hex[:8]}.db")
            self._is_temp = True
        else:
            self.db_path = os.path.abspath(db_path)
            self._temp_dir = None
            self._is_temp = False

        norm_path = self.db_path.replace("\\", "/")
        self.db_url = f"sqlite:///{norm_path}"
        assert_sandbox_isolated(self.db_url)

        self.engine = None
        self.SessionLocal = None

    def initialize_schema_with_alembic(self) -> None:
        """Executes Alembic migrations 0001, 0002, and 0003 up to head on the sandbox database."""
        assert_sandbox_isolated(self.db_url)
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        alembic_ini_path = os.path.join(backend_dir, "alembic.ini")

        cfg = Config(alembic_ini_path)
        cfg.set_main_option("sqlalchemy.url", self.db_url)
        cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))

        command.upgrade(cfg, "head")

        self.engine = create_engine(
            self.db_url,
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def seed_fixtures(self) -> None:
        """Seeds initial synthetic hospitals, users, consents, and donors for simulation scenarios."""
        assert_sandbox_isolated(self.db_url)
        session: Session = self.SessionLocal()
        try:
            # 1. Hospitals
            h1 = Hospital(
                id="city-hospital-001",
                name="City General Hospital",
                address="100 Hospital Way",
                city="Bengaluru",
                lat=12.9716,
                lng=77.5946,
                type="General Hospital",
                blood_bank_available=True,
                organ_transplant_center=True,
                emergency_bays=12,
                contact_number="+91-80-2222-0001",
                is_current_hospital=True,
            )
            h2 = Hospital(
                id="apollo-001",
                name="Apollo Hospital Bannerghatta",
                address="154/11 Bannerghatta Main Rd",
                city="Bengaluru",
                lat=12.8935,
                lng=77.5982,
                type="Speciality / Research",
                blood_bank_available=True,
                organ_transplant_center=True,
                emergency_bays=16,
                contact_number="+91-80-2222-0002",
                is_current_hospital=False,
            )
            session.add_all([h1, h2])

            # 2. Users
            pwd_hash = get_password_hash("LifeLink2026!Secure")
            from datetime import datetime, timezone
            now_dt = datetime.now(timezone.utc)
            now_iso = now_dt.isoformat()

            u_doc = User(
                id="usr-doc-01",
                name="Dr. Sim Physician",
                email="dr.sim@lifelink.org",
                hashed_password=pwd_hash,
                role="doctor",
                role_title="Chief Emergency Officer",
                hospital_id="city-hospital-001",
                hospital_name="City General Hospital",
                is_verified=True,
                created_at=now_dt,
            )
            u_staff = User(
                id="usr-staff-01",
                name="Nurse Staff Sim",
                email="staff.sim@lifelink.org",
                hashed_password=pwd_hash,
                role="hospital_staff",
                role_title="Emergency Coordinator",
                hospital_id="city-hospital-001",
                hospital_name="City General Hospital",
                is_verified=True,
                created_at=now_dt,
            )
            u_adm = User(
                id="usr-adm-01",
                name="Admin Sim Officer",
                email="admin.sim@lifelink.org",
                hashed_password=pwd_hash,
                role="admin",
                role_title="System Administrator",
                hospital_id="city-hospital-001",
                hospital_name="City General Hospital",
                is_verified=True,
                created_at=now_dt,
            )
            u_coord = User(
                id="usr-coord-01",
                name="Coord Sim Specialist",
                email="coord.sim@lifelink.org",
                hashed_password=pwd_hash,
                role="transplant_coordinator",
                role_title="Transplant Coordinator",
                hospital_id="city-hospital-001",
                hospital_name="City General Hospital",
                is_verified=True,
                created_at=now_dt,
            )
            u_amb = User(
                id="usr-amb-01",
                name="Operator Amb Sim",
                email="amb.sim@lifelink.org",
                hashed_password=pwd_hash,
                role="ambulance_operator",
                role_title="Ambulance Pilot",
                hospital_id="city-hospital-001",
                hospital_name="City General Hospital",
                is_verified=True,
                created_at=now_dt,
            )
            u_don1 = User(
                id="usr-don-01",
                name="Donor Valid Sim",
                email="donor1.sim@lifelink.org",
                hashed_password=pwd_hash,
                role="donor",
                role_title="Registered Donor",
                is_verified=True,
                created_at=now_dt,
            )
            u_don2 = User(
                id="usr-don-02",
                name="Donor Denied Sim",
                email="donor2.sim@lifelink.org",
                hashed_password=pwd_hash,
                role="donor",
                role_title="Registered Donor",
                is_verified=True,
                created_at=now_dt,
            )
            u_pat = User(
                id="usr-pat-01",
                name="Patient User Sim",
                email="patient.sim@lifelink.org",
                hashed_password=pwd_hash,
                role="patient",
                role_title="Patient",
                is_verified=True,
                created_at=now_dt,
            )
            session.add_all([u_doc, u_staff, u_adm, u_coord, u_amb, u_don1, u_don2, u_pat])

            # 3. Consents
            c1 = Consent(
                id="c-don-01",
                user_id="usr-don-01",
                live_location=True,
                emergency_communication=True,
                donation_requests=True,
                health_data_sharing=True,
                updated_at=now_iso,
            )
            c2 = Consent(
                id="c-don-02",
                user_id="usr-don-02",
                live_location=False,
                emergency_communication=False,  # Explicitly DENIED
                donation_requests=False,
                health_data_sharing=False,
                updated_at=now_iso,
            )
            session.add_all([c1, c2])

            # 4. Donors
            d1 = Donor(
                id="don-sim-01",
                user_id="usr-don-01",
                blood_group="O+",
                distance_km=2.4,
                eta_minutes=8,
                eligibility="eligible",
                response_probability=85,
                reliability_score=92,
                reachability_score=90,
                ai_rank=1,
                status="available",
                location_consent_granted=True,
                last_donation_days=95,
                historical_acceptance_rate=80,
                lat=12.9720,
                lng=77.5950,
                is_synthetic=False,
                data_provenance="production",
            )
            d2 = Donor(
                id="don-sim-02",
                user_id="usr-don-02",
                blood_group="O+",
                distance_km=3.1,
                eta_minutes=11,
                eligibility="eligible",
                response_probability=75,
                reliability_score=80,
                reachability_score=80,
                ai_rank=2,
                status="available",
                location_consent_granted=False,
                last_donation_days=120,
                historical_acceptance_rate=70,
                lat=12.9730,
                lng=77.5960,
                is_synthetic=False,
                data_provenance="production",
            )
            d3_syn = Donor(
                id="don-sim-syn-03",
                user_id=None,
                blood_group="O+",
                distance_km=1.5,
                eta_minutes=5,
                eligibility="eligible",
                response_probability=95,
                reliability_score=98,
                reachability_score=95,
                ai_rank=1,
                status="available",
                location_consent_granted=True,
                last_donation_days=80,
                historical_acceptance_rate=90,
                lat=12.9710,
                lng=77.5940,
                is_synthetic=True,
                data_provenance="synthetic",
            )
            d4_inelig = Donor(
                id="don-sim-inelig-04",
                user_id=None,
                blood_group="O+",
                distance_km=2.0,
                eta_minutes=7,
                eligibility="ineligible",
                eligibility_reason="Recent cardiac surgery",
                response_probability=50,
                reliability_score=50,
                reachability_score=50,
                ai_rank=99,
                status="unavailable",
                location_consent_granted=False,
                last_donation_days=30,
                historical_acceptance_rate=40,
                lat=12.9700,
                lng=77.5930,
                is_synthetic=False,
                data_provenance="production",
            )
            d5_bpos = Donor(
                id="don-sim-bpos-05",
                user_id=None,
                blood_group="B+",
                distance_km=2.2,
                eta_minutes=8,
                eligibility="eligible",
                response_probability=80,
                reliability_score=85,
                reachability_score=85,
                ai_rank=1,
                status="available",
                location_consent_granted=True,
                last_donation_days=110,
                historical_acceptance_rate=75,
                lat=12.9715,
                lng=77.5945,
                is_synthetic=False,
                data_provenance="production",
            )
            session.add_all([d1, d2, d3_syn, d4_inelig, d5_bpos])

            # 5. Ambulance
            amb = Ambulance(
                id="amb-sim-01",
                unit_number="KA-01-EM-1111",
                status="idle",
                hospital_id="city-hospital-001",
                lat=12.9716,
                lng=77.5946,
                updated_at=now_iso,
            )
            session.add(amb)

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_session(self) -> Session:
        return self.SessionLocal()

    def teardown(self) -> None:
        """Closes connections and cleans up temporary database artifacts."""
        if self.engine:
            self.engine.dispose()
        if self._is_temp and os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass
            if self._temp_dir and os.path.exists(self._temp_dir):
                try:
                    os.rmdir(self._temp_dir)
                except Exception:
                    pass
