import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.db.base import Base
from app.core.config import settings
from app.core.security import get_password_hash
from app.core.logging import logger
from app.models.user import User
from app.models.hospital import Hospital
from app.models.emergency import Emergency, EmergencyEvent
from app.models.donor import Donor
from app.models.organ import Organ
from app.models.ambulance import Ambulance
from app.models.audit import AuditLog
from app.models.consent import Consent


def init_db(db: Session) -> None:
    """
    Initializes database schema and populates development/demo dataset if configured.
    In development mode or when AUTO_SEED_DATA is enabled, ensures tables exist and
    seeds initial demo records in strict relational dependency order.
    """
    app_env = (settings.APP_ENV or "development").strip().lower()

    # 1. Ensure tables exist in development / SQLite environment (never in staging/production)
    if app_env not in ("staging", "production") and (
        app_env == "development" or settings.DATABASE_URL.startswith("sqlite")
    ):
        Base.metadata.create_all(bind=db.get_bind())
        try:
            import sqlalchemy as sa
            insp = sa.inspect(db.get_bind())
            if "audit_logs" in insp.get_table_names():
                existing_cols = {c["name"] for c in insp.get_columns("audit_logs")}
                with db.get_bind().connect() as conn:
                    if "previous_hash" not in existing_cols:
                        conn.execute(sa.text("ALTER TABLE audit_logs ADD COLUMN previous_hash VARCHAR(64)"))
                    if "record_hash" not in existing_cols:
                        conn.execute(sa.text("ALTER TABLE audit_logs ADD COLUMN record_hash VARCHAR(64)"))
                    conn.commit()
        except Exception as e:
            logger.warning(f"Schema synchronization note in init_db: {e}")

    # 2. Hard Seeding Guard: Demo-account seeding is strictly prohibited in staging and production
    # under all circumstances, even if AUTO_SEED_DATA is True.
    if app_env in ("staging", "production"):
        logger.info(
            f"Demo seeding guard active: Seeding is strictly blocked in '{settings.APP_ENV}' environment. "
            "Database schema and records must be managed independently."
        )
        return

    # 3. Development / Demo environment toggle
    if not settings.AUTO_SEED_DATA:
        logger.info("AUTO_SEED_DATA is False: skipping automatic demo data seeding.")
        return

    # 1. Hospitals (Independent Root)
    if db.query(Hospital).count() == 0:
        demo_hospitals = [
            Hospital(
                id="city-hospital-001",
                name="City General Hospital",
                address="100 Emergency Care Boulevard",
                city="Bengaluru",
                lat=12.9716,
                lng=77.5946,
                type="Level 1 Trauma Center",
                blood_bank_available=True,
                organ_transplant_center=True,
                emergency_bays=12,
                contact_number="+91-80-2222-0001",
                is_current_hospital=True,
            ),
            Hospital(
                id="apollo-001",
                name="Apollo Transplant Center",
                address="21 Health City Road",
                city="Bengaluru",
                lat=12.9352,
                lng=77.6245,
                type="Specialty Organ Center",
                blood_bank_available=True,
                organ_transplant_center=True,
                emergency_bays=8,
                contact_number="+91-80-2222-0002",
                is_current_hospital=False,
            ),
            Hospital(
                id="manipal-001",
                name="Manipal Heart & Emergency",
                address="98 HAL Airport Road",
                city="Bengaluru",
                lat=12.9592,
                lng=77.6543,
                type="Cardiac & Trauma Center",
                blood_bank_available=True,
                organ_transplant_center=True,
                emergency_bays=10,
                contact_number="+91-80-2222-0003",
                is_current_hospital=False,
            ),
            Hospital(
                id="fortis-001",
                name="Fortis Emergency Care",
                address="154/9 Bannerghatta Road",
                city="Bengaluru",
                lat=12.8984,
                lng=77.5986,
                type="Multi-Specialty Emergency",
                blood_bank_available=True,
                organ_transplant_center=False,
                emergency_bays=6,
                contact_number="+91-80-2222-0004",
                is_current_hospital=False,
            ),
        ]
        db.add_all(demo_hospitals)
        db.commit()

    # 2. Users (References Hospital)
    if db.query(User).count() == 0:
        demo_users = [
            User(
                id="usr-doc-001",
                name="Dr. Arjun Rao",
                email="doctor@lifelink.demo",
                hashed_password=get_password_hash("doctor123"),
                role="doctor",
                role_title="Senior Emergency Physician",
                hospital_id="city-hospital-001",
                hospital_name="City General Hospital",
                organization="City Healthcare Network",
                avatar=None,
                is_verified=True,
                last_login=datetime.now(timezone.utc).isoformat(),
                session_status="active",
            ),
            User(
                id="usr-stf-002",
                name="Meera Nair",
                email="staff@lifelink.demo",
                hashed_password=get_password_hash("staff123"),
                role="hospital_staff",
                role_title="Emergency Operations Lead",
                hospital_id="city-hospital-001",
                hospital_name="City General Hospital",
                organization="City Healthcare Network",
                avatar=None,
                is_verified=True,
                last_login=datetime.now(timezone.utc).isoformat(),
                session_status="active",
            ),
            User(
                id="usr-cor-003",
                name="Dr. Priya Sharma",
                email="transplant@lifelink.demo",
                hashed_password=get_password_hash("transplant123"),
                role="transplant_coordinator",
                role_title="Lead Transplant Coordinator",
                hospital_id="apollo-001",
                hospital_name="Apollo Transplant Center",
                organization="State Organ Sharing Network",
                avatar=None,
                is_verified=True,
                last_login=datetime.now(timezone.utc).isoformat(),
                session_status="active",
            ),
            User(
                id="usr-amb-004",
                name="Ramesh Kumar",
                email="ambulance@lifelink.demo",
                hashed_password=get_password_hash("ambulance123"),
                role="ambulance_operator",
                role_title="Critical Care Paramedic / Fleet Lead",
                hospital_id="city-hospital-001",
                hospital_name="City General Hospital",
                organization="Emergency Ambulance Services",
                avatar=None,
                is_verified=True,
                last_login=datetime.now(timezone.utc).isoformat(),
                session_status="active",
            ),
            User(
                id="usr-dnr-005",
                name="Vikram Singh",
                email="donor@lifelink.demo",
                hashed_password=get_password_hash("donor123"),
                role="donor",
                role_title="Verified Universal Blood Donor (O-)",
                hospital_id=None,
                hospital_name=None,
                organization=None,
                avatar=None,
                is_verified=True,
                last_login=datetime.now(timezone.utc).isoformat(),
                session_status="active",
            ),
            User(
                id="usr-dnr-006",
                name="Siddharth Sen",
                email="donor2@lifelink.demo",
                hashed_password=get_password_hash("donor123"),
                role="donor",
                role_title="Registered Blood Donor",
                hospital_id="city-hospital-001",
                hospital_name="City General Hospital",
                organization=None,
                avatar=None,
                is_verified=True,
                last_login=datetime.now(timezone.utc).isoformat(),
                session_status="active",
            ),
            User(
                id="usr-pat-006",
                name="Anita Roy",
                email="patient@lifelink.demo",
                hashed_password=get_password_hash("patient123"),
                role="patient",
                role_title="Registered Patient / Next of Kin",
                hospital_id="city-hospital-001",
                hospital_name="City General Hospital",
                organization=None,
                avatar=None,
                is_verified=True,
                last_login=datetime.now(timezone.utc).isoformat(),
                session_status="active",
            ),
            User(
                id="usr-adm-007",
                name="Sanjay Gupta",
                email="admin@lifelink.demo",
                hashed_password=get_password_hash("admin123"),
                role="admin",
                role_title="System Administrator & Governance Lead",
                hospital_id="city-hospital-001",
                hospital_name="City General Hospital",
                organization="LifeLink Health Authority",
                avatar=None,
                is_verified=True,
                last_login=datetime.now(timezone.utc).isoformat(),
                session_status="active",
            ),
        ]
        db.add_all(demo_users)
        db.commit()

    # 3. Consents (References User)
    if db.query(Consent).count() == 0:
        consents = [
            Consent(
                id="cns-001",
                user_id="usr-dnr-005",
                live_location=True,
                emergency_communication=True,
                donation_requests=True,
                health_data_sharing=True,
                updated_at=datetime.now(timezone.utc).isoformat(),
            ),
            Consent(
                id="cns-002",
                user_id="usr-pat-006",
                live_location=True,
                emergency_communication=True,
                donation_requests=False,
                health_data_sharing=True,
                updated_at=datetime.now(timezone.utc).isoformat(),
            ),
            Consent(
                id="cns-003",
                user_id="usr-dnr-006",
                live_location=True,
                emergency_communication=True,
                donation_requests=True,
                health_data_sharing=True,
                updated_at=datetime.now(timezone.utc).isoformat(),
            ),
        ]
        db.add_all(consents)
        db.commit()

    # 4. Donors (References User)
    if db.query(Donor).count() == 0:
        demo_donors = [
            Donor(
                id="D-101",
                user_id="usr-dnr-005",
                blood_group="O-",
                distance_km=3.2,
                eta_minutes=8,
                eligibility="eligible",
                response_probability=91,
                reliability_score=94,
                reachability_score=92,
                ai_rank=1,
                status="available",
                location_consent_granted=False,
                last_donation_days=92,
                historical_acceptance_rate=94,
                contacted_at=None,
                lat=12.975,
                lng=77.590,
            ),
            Donor(
                id="D-102",
                user_id="usr-dnr-006",
                blood_group="O-",
                distance_km=2.4,
                eta_minutes=6,
                eligibility="eligible",
                response_probability=88,
                reliability_score=90,
                reachability_score=90,
                ai_rank=2,
                status="available",
                location_consent_granted=True,
                last_donation_days=105,
                historical_acceptance_rate=88,
                lat=12.965,
                lng=77.595,
            ),
            Donor(
                id="D-103",
                user_id=None,
                blood_group="O-",
                distance_km=5.0,
                eta_minutes=14,
                eligibility="ineligible",
                eligibility_reason="Donation cooldown active (30 days since last donation)",
                response_probability=0,
                reliability_score=80,
                reachability_score=60,
                ai_rank=6,
                status="declined",
                location_consent_granted=False,
                last_donation_days=30,
                historical_acceptance_rate=80,
                lat=12.955,
                lng=77.605,
            ),
            Donor(
                id="D-104",
                user_id=None,
                blood_group="O-",
                distance_km=4.8,
                eta_minutes=12,
                eligibility="eligible",
                response_probability=84,
                reliability_score=88,
                reachability_score=85,
                ai_rank=2,
                status="available",
                location_consent_granted=True,
                last_donation_days=110,
                historical_acceptance_rate=88,
                lat=12.980,
                lng=77.585,
            ),
            Donor(
                id="D-109",
                user_id=None,
                blood_group="O-",
                distance_km=6.1,
                eta_minutes=16,
                eligibility="eligible",
                response_probability=78,
                reliability_score=82,
                reachability_score=79,
                ai_rank=3,
                status="available",
                location_consent_granted=False,
                last_donation_days=145,
                historical_acceptance_rate=82,
                lat=12.960,
                lng=77.610,
            ),
            Donor(
                id="D-115",
                user_id=None,
                blood_group="O-",
                distance_km=8.4,
                eta_minutes=22,
                eligibility="eligible",
                response_probability=65,
                reliability_score=74,
                reachability_score=68,
                ai_rank=4,
                status="available",
                location_consent_granted=False,
                last_donation_days=65,
                historical_acceptance_rate=74,
                lat=12.940,
                lng=77.620,
            ),
            Donor(
                id="D-122",
                user_id=None,
                blood_group="O-",
                distance_km=11.2,
                eta_minutes=28,
                eligibility="ineligible",
                eligibility_reason="Donation cooldown active (42 days since last donation)",
                response_probability=0,
                reliability_score=90,
                reachability_score=45,
                ai_rank=5,
                status="declined",
                location_consent_granted=False,
                last_donation_days=42,
                historical_acceptance_rate=90,
                lat=12.930,
                lng=77.630,
            ),
        ]
        db.add_all(demo_donors)
        db.commit()

    # 5. Emergencies (References Hospital)
    if db.query(Emergency).count() == 0:
        demo_emergencies = [
            Emergency(
                id="BL-102",
                type="blood",
                priority="critical",
                status="resource_search",
                hospital_id="city-hospital-001",
                hospital_name="City General Hospital",
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                description="Trauma bay 3: Acute hemorrhage from motor vehicle collision. Requires 3 units O- packed red blood cells immediately.",
                eta=11,
                assigned_resource_ids=json.dumps(["D-101", "D-104"]),
                blood_group="O-",
                units_required=3,
                location_lat=12.9716,
                location_lng=77.5946,
            ),
            Emergency(
                id="BL-103",
                type="blood",
                priority="high",
                status="coordinating",
                hospital_id="city-hospital-001",
                hospital_name="City General Hospital",
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                description="Emergency obstetrics: Postpartum hemorrhage in Labor & Delivery. Requires 2 units B+ blood.",
                eta=18,
                assigned_resource_ids=json.dumps(["D-201"]),
                blood_group="B+",
                units_required=2,
                location_lat=12.9716,
                location_lng=77.5946,
            ),
            Emergency(
                id="ORG-201",
                type="organ",
                priority="critical",
                status="resource_search",
                hospital_id="city-hospital-001",
                hospital_name="City General Hospital",
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                description="Donor heart available from Apollo Transplant Center (14.0 km). Cold ischemia clock active — 4h 32m remaining.",
                eta=14,
                assigned_resource_ids=json.dumps(["ORG-K-001"]),
                organ_type="kidney",
            ),
            Emergency(
                id="AMB-051",
                type="ambulance",
                priority="critical",
                status="coordinating",
                hospital_id="city-hospital-001",
                hospital_name="City General Hospital",
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                description="STEMI in transit via Unit AMB-042. Cath lab team activated. Dynamic green corridor route recommendation active.",
                eta=14,
                assigned_resource_ids=json.dumps(["amb-042"]),
                origin="City General Hospital",
                destination="Apollo Heart Institute",
            ),
            Emergency(
                id="RES-099",
                type="blood",
                priority="medium",
                status="resolved",
                hospital_id="city-hospital-001",
                hospital_name="City General Hospital",
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                resolved_at=datetime.now(timezone.utc).isoformat(),
                description="Elective surgical blood backup completed successfully.",
                eta=None,
                assigned_resource_ids=json.dumps([]),
                blood_group="A+",
                units_required=1,
            ),
        ]
        db.add_all(demo_emergencies)
        db.commit()

    # 6. Emergency Events (References Emergency)
    if db.query(EmergencyEvent).count() == 0:
        demo_events = [
            EmergencyEvent(
                id="evt-001",
                emergency_id="BL-102",
                timestamp=datetime.now(timezone.utc).isoformat(),
                actor="Dr. Arjun Rao",
                action="Emergency created: O- blood (3 units) for trauma surgery",
                resource="Trauma Bay 3",
                authorization="Doctor: Dr. Arjun Rao",
                status="success",
            ),
            EmergencyEvent(
                id="evt-002",
                emergency_id="BL-102",
                timestamp=datetime.now(timezone.utc).isoformat(),
                actor="Dynamic Radius Engine",
                action="Initial 2 km search radius yielded 1 donor — automatically expanded radius to 5 km",
                resource="Radius Engine",
                authorization="Automated Protocol",
                status="success",
            ),
            EmergencyEvent(
                id="evt-003",
                emergency_id="BL-102",
                timestamp=datetime.now(timezone.utc).isoformat(),
                actor="AI Ranking Engine",
                action="Ranked 5 candidate donors; dispatched SMS alert to Donor #D-101",
                resource="Donor #D-101",
                authorization="System Dispatch",
                status="success",
            ),
            EmergencyEvent(
                id="evt-004",
                emergency_id="AMB-051",
                timestamp=datetime.now(timezone.utc).isoformat(),
                actor="Navigation Engine",
                action="Evaluated 3 route options; Route B recommended via Ring Road (saves 4 min)",
                resource="Unit AMB-042",
                authorization="Automated Route Analyzer",
                status="success",
            ),
        ]
        db.add_all(demo_events)
        db.commit()

    # 7. Organs (References Hospital & User)
    if db.query(Organ).count() == 0:
        organs = [
            Organ(
                id="ORG-K-001",
                organ_type="kidney",
                source_hospital_id="apollo-001",
                source_hospital_name="Apollo Transplant Center",
                distance_km=14.0,
                eta_minutes=18,
                viability_remaining_seconds=16320,
                viability_total_seconds=129600,
                viability_level="normal",
                reachability_score=92,
                ai_recommendation="proceed",
                ai_rationale="Organ is within reachability threshold. ETA 18 min is well within viability window. High recipient compatibility.",
                status="clinical_review",
                clinical_review_status="pending",
                authorized_coordinator_id="usr-cor-003",
                lat=12.9352,
                lng=77.6245,
                available_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            ),
            Organ(
                id="ORG-L-002",
                organ_type="liver",
                source_hospital_id="manipal-001",
                source_hospital_name="Manipal Heart & Emergency",
                distance_km=22.5,
                eta_minutes=31,
                viability_remaining_seconds=28800,
                viability_total_seconds=43200,
                viability_level="normal",
                reachability_score=81,
                ai_recommendation="proceed",
                ai_rationale="Viability window safe. Route traffic is moderate. Transport feasibility score: 81/100.",
                status="available",
                clinical_review_status="approved",
                authorized_coordinator_id="usr-cor-003",
                lat=12.9592,
                lng=77.6543,
                available_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            ),
            Organ(
                id="ORG-H-003",
                organ_type="heart",
                source_hospital_id="fortis-001",
                source_hospital_name="Fortis Emergency Care",
                distance_km=8.1,
                eta_minutes=11,
                viability_remaining_seconds=10800,
                viability_total_seconds=21600,
                viability_level="warning",
                reachability_score=88,
                ai_recommendation="proceed",
                ai_rationale="Heart viability at 50% — immediate coordination recommended. ETA 11 min is within safe transport window. High urgency.",
                status="clinical_review",
                clinical_review_status="in_review",
                authorized_coordinator_id="usr-cor-003",
                lat=12.8984,
                lng=77.5986,
                available_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            ),
        ]
        db.add_all(organs)
        db.commit()

    # 8. Ambulances (References Hospital & Emergency)
    if db.query(Ambulance).count() == 0:
        routes_amb_042 = [
            {
                "id": "route-a",
                "label": "Route A",
                "distanceKm": 12.4,
                "etaMinutes": 18,
                "trafficCondition": "heavy",
                "roadFeasibility": "medium",
                "isAiRecommended": False,
                "aiRationale": "Heavy traffic on MG Road reduces feasibility.",
            },
            {
                "id": "route-b",
                "label": "Route B",
                "distanceKm": 10.8,
                "etaMinutes": 14,
                "trafficCondition": "normal",
                "roadFeasibility": "high",
                "isAiRecommended": True,
                "aiRationale": "Traffic: Normal. Distance: 10.8 km. ETA: 14 min. Road feasibility: High. Fastest estimated feasible route given current traffic.",
            },
            {
                "id": "route-c",
                "label": "Route C",
                "distanceKm": 11.6,
                "etaMinutes": 16,
                "trafficCondition": "moderate",
                "roadFeasibility": "high",
                "isAiRecommended": False,
                "aiRationale": "Moderate traffic on Outer Ring Road. Slightly longer ETA than Route B.",
            },
        ]
        ambulances = [
            Ambulance(
                id="amb-042",
                unit_number="AMB-042",
                status="en_route",
                driver_name="Operator",
                origin="City General Hospital",
                destination="Apollo Heart Institute",
                lat=12.965,
                lng=77.592,
                heading=45.0,
                speed_kmh=62.0,
                eta_minutes=14,
                routes_json=json.dumps(routes_amb_042),
                selected_route_id="route-b",
                hospital_id="city-hospital-001",
                emergency_id="AMB-051",
                dispatched_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            ),
            Ambulance(
                id="amb-031",
                unit_number="AMB-031",
                status="idle",
                driver_name=None,
                origin="City General Hospital",
                destination=None,
                lat=12.971,
                lng=77.587,
                hospital_id="city-hospital-001",
                updated_at=datetime.now(timezone.utc).isoformat(),
            ),
            Ambulance(
                id="amb-055",
                unit_number="AMB-055",
                status="transporting",
                driver_name=None,
                origin="Sunrise Clinic",
                destination="City General Hospital",
                lat=12.955,
                lng=77.608,
                heading=270.0,
                speed_kmh=48.0,
                eta_minutes=7,
                hospital_id="city-hospital-001",
                dispatched_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            ),
            Ambulance(
                id="amb-019",
                unit_number="AMB-019",
                status="at_hospital",
                driver_name=None,
                origin="Emergency Scene",
                destination="City General Hospital",
                lat=12.971,
                lng=77.587,
                hospital_id="city-hospital-001",
                arrived_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            ),
        ]
        db.add_all(ambulances)
        db.commit()

    # 9. Audit Logs (Independent Durable Records)
    if db.query(AuditLog).count() == 0:
        logs = [
            AuditLog(
                id="audit-001",
                timestamp=datetime.now(timezone.utc).isoformat(),
                actor="Dr. Sarah Patel",
                actor_type="user",
                action="Created Blood Emergency SOS",
                resource="Blood Emergency #BL-102",
                resource_id="BL-102",
                authorization="Role: Doctor",
                status="success",
                module="blood",
                session_id="sess-abc123",
            ),
            AuditLog(
                id="audit-002",
                timestamp=datetime.now(timezone.utc).isoformat(),
                actor="AI Orchestrator",
                actor_type="ai",
                action="LLM parsed emergency intent",
                resource="Blood Emergency #BL-102",
                resource_id="BL-102",
                authorization="System Process",
                status="success",
                module="blood",
            ),
            AuditLog(
                id="audit-007",
                timestamp=datetime.now(timezone.utc).isoformat(),
                actor="Donor #D-104",
                actor_type="donor",
                action="Location consent granted",
                resource="Donor #D-104",
                resource_id="D-104",
                authorization="Consent Granted",
                status="success",
                module="blood",
            ),
            AuditLog(
                id="audit-008",
                timestamp=datetime.now(timezone.utc).isoformat(),
                actor="Dr. Rajan Mehta",
                actor_type="user",
                action="Ambulance dispatch requested",
                resource="Ambulance Emergency #AMB-051",
                resource_id="AMB-051",
                authorization="Role: Doctor",
                status="success",
                module="ambulance",
                session_id="sess-def456",
            ),
        ]
        db.add_all(logs)
        db.commit()
