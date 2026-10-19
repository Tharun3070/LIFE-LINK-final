from enum import Enum
from typing import List, Dict


class UserRole(str, Enum):
    DOCTOR = "doctor"
    HOSPITAL_STAFF = "hospital_staff"
    TRANSPLANT_COORDINATOR = "transplant_coordinator"
    AMBULANCE_OPERATOR = "ambulance_operator"
    DONOR = "donor"
    PATIENT = "patient"
    ADMIN = "admin"


class Permission(str, Enum):
    # Command Center & General
    VIEW_COMMAND_CENTER = "view_command_center"
    VIEW_ANALYTICS = "view_analytics"
    VIEW_LIVE_MAP = "view_live_map"
    VIEW_AUDIT_LOGS = "view_audit_logs"

    # Blood Emergencies & Donors
    CREATE_BLOOD_EMERGENCY = "create_blood_emergency"
    MANAGE_BLOOD_EMERGENCY = "manage_blood_emergency"
    DONOR_READ = "donor:read"
    DONOR_CONTACT = "donor:contact"
    DONOR_LOCATION = "donor:location"
    MANAGE_DONOR_PROFILE = "manage_donor_profile"
    MANAGE_DONOR_CONSENT = "manage_donor_consent"

    # Organs
    VIEW_ORGAN_INTELLIGENCE = "view_organ_intelligence"
    REQUEST_CLINICAL_REVIEW = "request_clinical_review"
    PERFORM_CLINICAL_REVIEW = "perform_clinical_review"
    ORGAN_READ = "organ:read"

    # Ambulances
    MANAGE_AMBULANCE = "manage_ambulance"
    AMBULANCE_UPDATE_LOCATION = "ambulance:update_location"
    AMBULANCE_UPDATE_STATUS = "ambulance:update_status"

    # Patient
    VIEW_PATIENT_STATUS = "view_patient_status"

    # Hospital & System Admin
    HOSPITAL_READ = "hospital:read"
    HOSPITAL_MANAGE = "hospital:manage"
    MANAGE_SYSTEM_USERS = "manage_system_users"
    MANAGE_SYSTEM_CONFIG = "manage_system_config"


# Complete mapping of roles to permissions matching frontend contracts exactly
ROLE_PERMISSIONS: Dict[UserRole, List[Permission]] = {
    UserRole.DOCTOR: [
        Permission.VIEW_COMMAND_CENTER,
        Permission.CREATE_BLOOD_EMERGENCY,
        Permission.MANAGE_BLOOD_EMERGENCY,
        Permission.DONOR_READ,
        Permission.DONOR_CONTACT,
        Permission.VIEW_ORGAN_INTELLIGENCE,
        Permission.REQUEST_CLINICAL_REVIEW,
        Permission.MANAGE_AMBULANCE,
        Permission.VIEW_LIVE_MAP,
        Permission.VIEW_ANALYTICS,
        Permission.VIEW_AUDIT_LOGS,
        Permission.HOSPITAL_READ,
        Permission.ORGAN_READ,
    ],
    UserRole.HOSPITAL_STAFF: [
        Permission.VIEW_COMMAND_CENTER,
        Permission.CREATE_BLOOD_EMERGENCY,
        Permission.MANAGE_BLOOD_EMERGENCY,
        Permission.DONOR_READ,
        Permission.DONOR_CONTACT,
        Permission.MANAGE_AMBULANCE,
        Permission.VIEW_LIVE_MAP,
        Permission.HOSPITAL_READ,
    ],
    UserRole.TRANSPLANT_COORDINATOR: [
        Permission.VIEW_COMMAND_CENTER,
        Permission.VIEW_ORGAN_INTELLIGENCE,
        Permission.REQUEST_CLINICAL_REVIEW,
        Permission.PERFORM_CLINICAL_REVIEW,
        Permission.VIEW_LIVE_MAP,
        Permission.VIEW_AUDIT_LOGS,
        Permission.ORGAN_READ,
        Permission.HOSPITAL_READ,
    ],
    UserRole.AMBULANCE_OPERATOR: [
        Permission.MANAGE_AMBULANCE,
        Permission.AMBULANCE_UPDATE_LOCATION,
        Permission.AMBULANCE_UPDATE_STATUS,
        Permission.VIEW_LIVE_MAP,
    ],
    UserRole.DONOR: [
        Permission.MANAGE_DONOR_PROFILE,
        Permission.MANAGE_DONOR_CONSENT,
    ],
    UserRole.PATIENT: [
        Permission.VIEW_PATIENT_STATUS,
    ],
    UserRole.ADMIN: [
        Permission.VIEW_COMMAND_CENTER,
        Permission.CREATE_BLOOD_EMERGENCY,
        Permission.MANAGE_BLOOD_EMERGENCY,
        Permission.DONOR_READ,
        Permission.DONOR_CONTACT,
        Permission.DONOR_LOCATION,
        Permission.VIEW_ORGAN_INTELLIGENCE,
        Permission.REQUEST_CLINICAL_REVIEW,
        Permission.PERFORM_CLINICAL_REVIEW,
        Permission.ORGAN_READ,
        Permission.MANAGE_AMBULANCE,
        Permission.AMBULANCE_UPDATE_LOCATION,
        Permission.AMBULANCE_UPDATE_STATUS,
        Permission.VIEW_LIVE_MAP,
        Permission.VIEW_ANALYTICS,
        Permission.VIEW_AUDIT_LOGS,
        Permission.MANAGE_DONOR_PROFILE,
        Permission.MANAGE_DONOR_CONSENT,
        Permission.VIEW_PATIENT_STATUS,
        Permission.HOSPITAL_READ,
        Permission.HOSPITAL_MANAGE,
        Permission.MANAGE_SYSTEM_USERS,
        Permission.MANAGE_SYSTEM_CONFIG,
    ],
}
