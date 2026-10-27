"""
LifeLink Privacy and Data Minimization Service.
Ensures zero unnecessary exposure of sensitive patient and donor personally identifiable information (PII)
to external or internal Large Language Models.
Authoritative candidate matching and clinical rules remain inside deterministic backend services.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Set
from pydantic import BaseModel, Field

from app.services.matching_engine import CandidateEvaluation


class SanitizedCandidateSummary(BaseModel):
    candidate_pseudonym: str = Field(..., description="Anonymized label, e.g. Candidate #1")
    blood_group: str = Field(..., description="Compatible ABO/Rh blood group")
    distance_bracket: str = Field(..., description="Coarse distance bracket, never raw coordinates")
    eta_bracket: str = Field(..., description="Estimated travel time bracket")
    availability_status: str = Field(..., description="Operational status: available, on-call")
    relative_rank: int = Field(..., description="Relative operational suitability rank")


class SanitizedMatchingContext(BaseModel):
    request_type: str = Field(default="blood_emergency")
    requested_blood_group: str
    requested_component: str = Field(default="red_blood_cells")
    coarse_location: str = Field(..., description="Coarse city, district, or hospital center name")
    units_requested: Optional[int] = None
    eligible_candidate_count: int
    excluded_candidate_count: int
    exclusion_breakdown: Dict[str, int] = Field(default_factory=dict)
    availability_verification: str = Field(
        default="pending",
        description="Verification state: pending, in_progress, or verified"
    )
    candidates: List[SanitizedCandidateSummary] = Field(default_factory=list)
    clinical_evidence: List[Dict[str, str]] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SanitizedEmergencyContext(BaseModel):
    emergency_type: str
    severity: str
    blood_group_required: Optional[str] = None
    blood_component: str = "red_blood_cells"
    coarse_location: str
    is_critical: bool = False
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class LLMValidationResult(BaseModel):
    is_valid: bool
    sanitized_text: str
    safety_flags: List[str] = Field(default_factory=list)
    redaction_applied: bool = False
    hallucination_detected: bool = False
    crossmatch_disclaimer_appended: bool = False


# Regex patterns for detecting and scrubbing potential PII / sensitive data leaks
PHONE_REGEX = re.compile(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\b[6-9]\d{9}\b')
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
COORDINATE_REGEX = re.compile(r'\b-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}\b')
STREET_ADDRESS_REGEX = re.compile(r'\b(?:\d{1,4}\s+[A-Za-z0-9\s,.-]+(?:Street|St|Avenue|Ave|Road|Rd|Nagar|Colony|Layout|Cross|Main))\b', re.IGNORECASE)

FORBIDDEN_PAYLOAD_KEYS: Set[str] = {
    "phone", "phone_number", "contact_number", "mobile", "email",
    "donor_name", "patient_name", "first_name", "last_name", "full_name",
    "address", "residential_address", "street", "pincode", "zip_code",
    "lat", "lng", "latitude", "longitude", "coordinates",
    "aadhaar", "ssn", "national_id", "govt_id",
    "password", "hashed_password", "token", "access_token", "secret", "api_key"
}

# Explicit allowlist of permissible attributes in language model context prompts
ALLOWED_PROMPT_KEYS: Set[str] = {
    "request_type", "requested_blood_group", "requested_component",
    "coarse_location", "units_requested", "eligible_candidate_count",
    "excluded_candidate_count", "exclusion_breakdown", "availability_verification",
    "candidates", "candidate_pseudonym", "blood_group", "distance_bracket",
    "eta_bracket", "availability_status", "relative_rank",
    "clinical_evidence", "title", "organization", "excerpt",
    "generated_at", "query", "notes", "is_critical", "emergency_type", "severity",
    "incompatible_blood_group", "medical_deferral", "operationally_unavailable"
}

MANDATORY_CLINICAL_DISCLAIMER = (
    "CLINICAL NOTICE: Deterministic donor matching provides operational coordination support only. "
    "Actual transfusion requires mandatory hospital blood-banking protocols, formal pre-transfusion "
    "crossmatching, and verified clinical physician authorization."
)


class PrivacySanitizationService:
    """
    Enforces the privacy boundary between backend healthcare data and language model interfaces.
    Applies strict data minimization, payload allowlisting, and PII interception.
    Note: Regex and pattern scrubbing are defense-in-depth measures and do not replace strict authorization.
    """

    @staticmethod
    def scrub_free_text_pii(text: str) -> str:
        """
        Scrubs phone numbers, email addresses, exact GPS coordinates, and street addresses
        from free-text clinical notes or queries prior to model processing.
        """
        if not text:
            return ""
        scrubbed = PHONE_REGEX.sub("[PROTECTED PHONE]", text)
        scrubbed = EMAIL_REGEX.sub("[PROTECTED EMAIL]", scrubbed)
        scrubbed = COORDINATE_REGEX.sub("[PROTECTED COORDINATES]", scrubbed)
        scrubbed = STREET_ADDRESS_REGEX.sub("[PROTECTED ADDRESS]", scrubbed)
        return scrubbed


    @staticmethod
    def _to_distance_bracket(dist_km: Optional[float]) -> str:
        """Converts exact floating-point kilometer distances into coarse privacy-safe brackets."""
        if dist_km is None:
            return "location_unavailable"
        if dist_km < 3.0:
            return "under_3_km"
        elif dist_km < 5.0:
            return "3_to_5_km"
        elif dist_km < 10.0:
            return "5_to_10_km"
        elif dist_km < 20.0:
            return "10_to_20_km"
        else:
            return "beyond_20_km"

    @staticmethod
    def _to_eta_bracket(eta_minutes: Optional[int]) -> str:
        """Converts minute ETAs into coarse heuristic transit brackets."""
        if eta_minutes is None:
            return "eta_unavailable"
        if eta_minutes < 15:
            return "within_15_mins"
        elif eta_minutes < 30:
            return "15_to_30_mins"
        elif eta_minutes < 60:
            return "30_to_60_mins"
        else:
            return "over_60_mins"

    def build_sanitized_matching_context(
        self,
        recipient_blood_group: str,
        component: str,
        location_name: str,
        eligible_candidates: List[CandidateEvaluation],
        excluded_candidates: List[CandidateEvaluation],
        units_requested: Optional[int] = None,
        clinical_evidence: Optional[List[Dict[str, str]]] = None,
        max_candidate_summaries: int = 5,
    ) -> SanitizedMatchingContext:
        """
        Transforms raw candidate evaluations into a sanitized context structure.
        Strips all donor names, phone numbers, emails, exact coordinates, and personal history.
        """
        # Aggregate exclusion reasons
        exclusion_breakdown: Dict[str, int] = {}
        for exc in excluded_candidates:
            category = "incompatible_blood_group"
            if not exc.is_eligible:
                category = "medical_deferral"
            elif not exc.is_available:
                category = "operationally_unavailable"
            exclusion_breakdown[category] = exclusion_breakdown.get(category, 0) + 1

        # Anonymize eligible candidates into ranked pseudonyms with coarse brackets
        sanitized_candidates: List[SanitizedCandidateSummary] = []
        for idx, cand in enumerate(eligible_candidates[:max_candidate_summaries], start=1):
            sanitized_candidates.append(
                SanitizedCandidateSummary(
                    candidate_pseudonym=f"Candidate #{idx}",
                    blood_group=cand.donor.blood_group,
                    distance_bracket=self._to_distance_bracket(cand.distance_km),
                    eta_bracket=self._to_eta_bracket(cand.eta_minutes),
                    availability_status=(cand.donor.status or "unknown").lower(),
                    relative_rank=idx,
                )
            )

        # Sanitize clinical evidence: pass only title, issuing authority, and sanitized excerpt
        clean_evidence: List[Dict[str, str]] = []
        if clinical_evidence:
            for ev in clinical_evidence:
                clean_evidence.append({
                    "title": ev.get("title", "Clinical Protocol"),
                    "organization": ev.get("organization", "Healthcare Authority"),
                    "excerpt": ev.get("content", ev.get("excerpt", ""))[:300],
                })

        # Coarse location: ensure location_name does not contain exact coordinates or door numbers
        clean_loc = re.sub(r'\b\d{1,4}[A-Za-z]?,?\s*', '', location_name or "").strip()
        if not clean_loc:
            clean_loc = "Coimbatore Medical Region"

        return SanitizedMatchingContext(
            request_type="blood_emergency",
            requested_blood_group=recipient_blood_group.upper(),
            requested_component=component.lower(),
            coarse_location=clean_loc,
            units_requested=units_requested,
            eligible_candidate_count=len(eligible_candidates),
            excluded_candidate_count=len(excluded_candidates),
            exclusion_breakdown=exclusion_breakdown,
            availability_verification="pending",
            candidates=sanitized_candidates,
            clinical_evidence=clean_evidence,
        )

    def sanitize_emergency_context(
        self,
        emergency_type: str,
        severity: str,
        blood_group: Optional[str] = None,
        component: str = "red_blood_cells",
        location: Optional[str] = None,
        is_critical: bool = False,
    ) -> SanitizedEmergencyContext:
        """
        Sanitizes emergency metadata for LLM assistance, omitting any patient name or identity.
        """
        clean_loc = location or "Hospital Emergency Dept"
        # Strip exact street address components if present
        clean_loc = STREET_ADDRESS_REGEX.sub("Metropolitan Area", clean_loc)
        clean_loc = COORDINATE_REGEX.sub("[Location Coordinates Protected]", clean_loc)

        return SanitizedEmergencyContext(
            emergency_type=emergency_type,
            severity=severity,
            blood_group_required=blood_group.upper() if blood_group else None,
            blood_component=component,
            coarse_location=clean_loc,
            is_critical=is_critical,
        )

    def audit_context_payload(self, payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Verifies that a dictionary intended for LLM ingestion strictly complies with privacy rules:
        1. No forbidden PII keys (phone, email, coordinates, donor names, tokens).
        2. All payload keys belong to the explicit ALLOWED_PROMPT_KEYS allowlist.
        3. String values do not contain raw phone numbers, email addresses, or unmasked coordinates.
        Returns (is_clean, violations).
        """
        violations: List[str] = []

        def _recursive_check(data: Any, path: str = ""):
            if isinstance(data, dict):
                for k, v in data.items():
                    current_path = f"{path}.{k}" if path else k
                    clean_k = k.lower().strip()
                    if clean_k in FORBIDDEN_PAYLOAD_KEYS:
                        violations.append(f"Forbidden PII key detected: {current_path}")
                    elif clean_k not in ALLOWED_PROMPT_KEYS and not clean_k.startswith("candidate_"):
                        violations.append(f"Unapproved key outside prompt allowlist: {current_path}")

                    _recursive_check(v, current_path)
            elif isinstance(data, list):
                for idx, item in enumerate(data):
                    _recursive_check(item, f"{path}[{idx}]")
            elif isinstance(data, str):
                if PHONE_REGEX.search(data):
                    violations.append(f"Embedded phone number detected in value at {path}")
                elif EMAIL_REGEX.search(data):
                    violations.append(f"Embedded email address detected in value at {path}")
                elif COORDINATE_REGEX.search(data):
                    violations.append(f"Embedded raw geographic coordinates detected in value at {path}")

        _recursive_check(payload)
        return len(violations) == 0, violations

    def validate_and_sanitize_llm_response(
        self,
        response_text: str,
        context: Optional[SanitizedMatchingContext] = None,
    ) -> LLMValidationResult:
        """
        Validates model output to ensure:
        1. No PII was reflected or leaked (phone, email, coordinates).
        2. No hallucinated donor counts when zero candidates exist.
        3. No claims that a donor has accepted or dispatched when verification is pending.
        4. Transfusion clinical disclaimer is explicitly included.
        """
        safety_flags: List[str] = []
        sanitized_text = response_text or ""
        redaction_applied = False
        hallucination_detected = False

        # 1. Scrub leaked phone numbers
        if PHONE_REGEX.search(sanitized_text):
            sanitized_text = PHONE_REGEX.sub("[PROTECTED PHONE NUMBER]", sanitized_text)
            safety_flags.append("PII_REDACTED_PHONE")
            redaction_applied = True

        # 2. Scrub leaked email addresses
        if EMAIL_REGEX.search(sanitized_text):
            sanitized_text = EMAIL_REGEX.sub("[PROTECTED EMAIL]", sanitized_text)
            safety_flags.append("PII_REDACTED_EMAIL")
            redaction_applied = True

        # 3. Scrub raw coordinates
        if COORDINATE_REGEX.search(sanitized_text):
            sanitized_text = COORDINATE_REGEX.sub("[PROTECTED COORDINATES]", sanitized_text)
            safety_flags.append("PII_REDACTED_COORDINATES")
            redaction_applied = True

        # 4. Context Grounding Check: Zero Candidate Hallucination
        if context is not None:
            if context.eligible_candidate_count == 0:
                # Check if model falsely claimed candidates were found or dispatched
                positive_claims = ["candidate available", "donors ready", "matched donor", "donor on the way", "donor dispatched"]
                if any(claim in sanitized_text.lower() for claim in positive_claims):
                    hallucination_detected = True
                    safety_flags.append("HALLUCINATION_FALSE_DONORS_CLAIMED")
                    sanitized_text = (
                        f"Database records confirm that zero eligible candidates currently match the requested "
                        f"{context.requested_blood_group} ({context.requested_component}) in {context.coarse_location}. "
                        f"Regional blood bank inventory reserves should be queried immediately."
                    )

            # 5. Context Grounding Check: Claiming acceptance while verification is pending
            if context.availability_verification == "pending":
                unverified_claims = ["has accepted", "confirmed arrival", "is currently en route", "has agreed to donate"]
                if any(claim in sanitized_text.lower() for claim in unverified_claims):
                    hallucination_detected = True
                    safety_flags.append("UNVERIFIED_ACCEPTANCE_CLAIM_CORRECTED")
                    sanitized_text += (
                        "\n\n[System Note: Donor operational availability remains PENDING dispatch response "
                        "and has NOT yet been confirmed by physical responder telemetry.]"
                    )

        # 6. Ensure mandatory clinical crossmatch disclaimer
        disclaimer_appended = False
        if "crossmatching" not in sanitized_text.lower() and "clinical physician" not in sanitized_text.lower():
            sanitized_text = f"{sanitized_text}\n\n{MANDATORY_CLINICAL_DISCLAIMER}"
            disclaimer_appended = True

        is_valid = len(safety_flags) == 0 or not hallucination_detected

        return LLMValidationResult(
            is_valid=is_valid,
            sanitized_text=sanitized_text,
            safety_flags=safety_flags,
            redaction_applied=redaction_applied,
            hallucination_detected=hallucination_detected,
            crossmatch_disclaimer_appended=disclaimer_appended,
        )


privacy_service = PrivacySanitizationService()
