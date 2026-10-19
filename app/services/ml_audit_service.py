"""
LifeLink ML Readiness & Interaction Data Audit Service
File: backend/app/services/ml_audit_service.py

Performs read-only audit of emergency donor interactions for machine learning feasibility.
Validates:
1. Volume and diversity (total interactions, distinct emergencies, distinct candidate donors).
2. Provenance separation (synthetic simulation / test fixture vs. production).
3. Lifecycle state distributions (contact, response, acceptance, completion).
4. Data integrity and timestamp consistency (no future leakage, positive latencies, logical chronology).
5. Target-specific training sample eligibility (Response Propensity, Acceptance, Completion).
6. Class imbalance and minimum viable dataset (MVD) threshold gating (minimum 2,500 production records).
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct

from app.models.interaction import DonorEmergencyInteraction


# Minimum Viable Dataset (MVD) threshold required before training any supervised model
MINIMUM_VIABLE_INTERACTIONS_THRESHOLD = 2500
MINIMUM_DISTINCT_EMERGENCIES_THRESHOLD = 250


class MLAuditService:
    @staticmethod
    def audit_interactions(db: Session) -> Dict[str, Any]:
        """
        Executes a comprehensive, non-mutating audit of all interaction records.
        Returns a structured dictionary of quality metrics, label eligibility, and readiness verdicts.
        """
        all_interactions: List[DonorEmergencyInteraction] = db.query(DonorEmergencyInteraction).all()
        total_records = len(all_interactions)

        # 1. Volume & Diversity
        distinct_emergencies = len(set(i.emergency_id for i in all_interactions))
        distinct_donors = len(set(i.donor_id for i in all_interactions))

        # 2. Provenance Separation
        synthetic_count = sum(1 for i in all_interactions if i.is_synthetic or i.data_provenance != "production")
        production_count = total_records - synthetic_count

        provenance_breakdown: Dict[str, int] = {}
        for i in all_interactions:
            prov = i.data_provenance or "unknown"
            provenance_breakdown[prov] = provenance_breakdown.get(prov, 0) + 1

        # 3. Lifecycle & Outcome Distributions
        contact_status_counts: Dict[str, int] = {}
        response_status_counts: Dict[str, int] = {}
        acceptance_status_counts: Dict[str, int] = {}
        completion_status_counts: Dict[str, int] = {}

        for i in all_interactions:
            contact_status_counts[i.contact_status] = contact_status_counts.get(i.contact_status, 0) + 1
            response_status_counts[i.response_status] = response_status_counts.get(i.response_status, 0) + 1
            acceptance_status_counts[i.acceptance_status] = acceptance_status_counts.get(i.acceptance_status, 0) + 1
            completion_status_counts[i.completion_status] = completion_status_counts.get(i.completion_status, 0) + 1

        # 4. Timestamp & Data Integrity Checks
        missing_attempt_timestamps = 0
        missing_response_timestamps = 0
        negative_latencies = 0
        chronology_errors = 0
        conflicting_states = 0
        observed_latencies: List[int] = []

        # Duplicate checking: multiple active pending interactions for same (emergency, donor)
        pair_counts: Dict[str, int] = {}
        duplicate_pending_pairs = 0

        for i in all_interactions:
            # Timestamp completeness
            if i.contact_status in ("attempted", "delivered") and not i.contact_attempted_at:
                missing_attempt_timestamps += 1
            if i.response_status == "responded" and not i.responded_at:
                missing_response_timestamps += 1

            # Latency sanity
            if i.response_latency_seconds is not None:
                if i.response_latency_seconds < 0:
                    negative_latencies += 1
                else:
                    observed_latencies.append(i.response_latency_seconds)

            # Chronology: responded_at must be >= contact_attempted_at
            if i.contact_attempted_at and i.responded_at:
                try:
                    att_dt = datetime.fromisoformat(i.contact_attempted_at)
                    resp_dt = datetime.fromisoformat(i.responded_at)
                    if resp_dt < att_dt:
                        chronology_errors += 1
                except Exception:
                    chronology_errors += 1

            # Conflicting state checks
            if i.acceptance_status == "accepted" and i.response_status == "pending":
                conflicting_states += 1
            if i.completion_status == "completed" and i.acceptance_status != "accepted":
                conflicting_states += 1

            # Duplicate active pairs
            if i.completion_status == "pending":
                key = f"{i.emergency_id}:{i.donor_id}"
                pair_counts[key] = pair_counts.get(key, 0) + 1
                if pair_counts[key] > 1:
                    duplicate_pending_pairs += 1

        # Latency statistics
        latency_coverage_pct = round((len(observed_latencies) / total_records * 100), 2) if total_records > 0 else 0.0
        mean_latency = round(sum(observed_latencies) / len(observed_latencies), 1) if observed_latencies else None
        min_latency = min(observed_latencies) if observed_latencies else None
        max_latency = max(observed_latencies) if observed_latencies else None

        # 5. Potential ML Prediction Target Eligibility (STRICT PROVENANCE ISOLATION)
        # Production-only records are evaluated for legitimate training readiness.
        production_records = [i for i in all_interactions if not i.is_synthetic and i.data_provenance == "production"]

        # Target A: Response Propensity P(Response | Dispatch Attempt)
        # Excludes pending interactions to prevent treating pending as negative.
        eligible_target_a = [
            i for i in production_records
            if i.contact_status in ("attempted", "delivered")
            and i.response_status in ("responded", "no_response", "expired")
        ]
        target_a_positive = sum(1 for i in eligible_target_a if i.response_status == "responded")
        target_a_negative = len(eligible_target_a) - target_a_positive

        # Target B: Acceptance Propensity P(Accepted | Responded)
        eligible_target_b = [
            i for i in production_records
            if i.response_status == "responded"
            and i.acceptance_status in ("accepted", "declined")
        ]
        target_b_accepted = sum(1 for i in eligible_target_b if i.acceptance_status == "accepted")
        target_b_declined = len(eligible_target_b) - target_b_accepted

        # Target C: Donation Completion P(Completed | Accepted)
        eligible_target_c = [
            i for i in production_records
            if i.acceptance_status == "accepted"
            and i.completion_status in ("completed", "medically_deferred", "did_not_arrive")
        ]
        target_c_completed = sum(1 for i in eligible_target_c if i.completion_status == "completed")
        target_c_uncompleted = len(eligible_target_c) - target_c_completed

        # 6. Readiness Evaluation & Verdict
        has_sufficient_records = len(eligible_target_a) >= MINIMUM_VIABLE_INTERACTIONS_THRESHOLD
        has_sufficient_emergencies = distinct_emergencies >= MINIMUM_DISTINCT_EMERGENCIES_THRESHOLD
        has_zero_integrity_flaws = (
            negative_latencies == 0
            and chronology_errors == 0
            and conflicting_states == 0
            and duplicate_pending_pairs == 0
        )

        is_ready_for_training = has_sufficient_records and has_sufficient_emergencies and has_zero_integrity_flaws

        blocking_reasons: List[str] = []
        if total_records == 0:
            blocking_reasons.append("Interaction ledger is empty (0 records).")
        elif production_count == 0:
            blocking_reasons.append("Zero production interaction records found. Existing records are synthetic benchmark fixtures.")
        elif not has_sufficient_records:
            blocking_reasons.append(
                f"Insufficient production response-labeled interactions ({len(eligible_target_a)} available; "
                f"minimum {MINIMUM_VIABLE_INTERACTIONS_THRESHOLD} required to prevent severe overfitting)."
            )

        if not has_sufficient_emergencies and total_records > 0:
            blocking_reasons.append(
                f"Insufficient distinct emergency diversity ({distinct_emergencies} available; "
                f"minimum {MINIMUM_DISTINCT_EMERGENCIES_THRESHOLD} required to ensure generalizability)."
            )

        if not has_zero_integrity_flaws:
            blocking_reasons.append("Data integrity anomalies detected (chronology, negative latencies, or duplicate pairs).")

        return {
            "audit_timestamp": datetime.now().isoformat(),
            "volume": {
                "total_interactions": total_records,
                "distinct_emergencies": distinct_emergencies,
                "distinct_donors": distinct_donors,
            },
            "provenance": {
                "production_records": production_count,
                "synthetic_records": synthetic_count,
                "breakdown": provenance_breakdown,
            },
            "lifecycle_outcomes": {
                "contact_status": contact_status_counts,
                "response_status": response_status_counts,
                "acceptance_status": acceptance_status_counts,
                "completion_status": completion_status_counts,
            },
            "data_integrity": {
                "missing_attempt_timestamps": missing_attempt_timestamps,
                "missing_response_timestamps": missing_response_timestamps,
                "negative_latencies": negative_latencies,
                "chronology_errors": chronology_errors,
                "conflicting_states": conflicting_states,
                "duplicate_pending_pairs": duplicate_pending_pairs,
                "passed_integrity_checks": has_zero_integrity_flaws,
            },
            "latency_metrics": {
                "observed_count": len(observed_latencies),
                "coverage_pct": latency_coverage_pct,
                "mean_seconds": mean_latency,
                "min_seconds": min_latency,
                "max_seconds": max_latency,
            },
            "prediction_targets": {
                "target_a_response_propensity": {
                    "eligible_records": len(eligible_target_a),
                    "positive_count (responded)": target_a_positive,
                    "negative_count (no_response/expired)": target_a_negative,
                    "positive_ratio": round(target_a_positive / len(eligible_target_a), 3) if eligible_target_a else 0.0,
                },
                "target_b_acceptance_propensity": {
                    "eligible_records": len(eligible_target_b),
                    "positive_count (accepted)": target_b_accepted,
                    "negative_count (declined)": target_b_declined,
                    "positive_ratio": round(target_b_accepted / len(eligible_target_b), 3) if eligible_target_b else 0.0,
                },
                "target_c_donation_completion": {
                    "eligible_records": len(eligible_target_c),
                    "positive_count (completed)": target_c_completed,
                    "negative_count (deferred/no_show)": target_c_uncompleted,
                    "positive_ratio": round(target_c_completed / len(eligible_target_c), 3) if eligible_target_c else 0.0,
                },
            },
            "verdict": {
                "is_ready_for_training": is_ready_for_training,
                "status": "READY_FOR_MODEL_TRAINING" if is_ready_for_training else "NOT_READY_FOR_MODEL_TRAINING",
                "minimum_required_records": MINIMUM_VIABLE_INTERACTIONS_THRESHOLD,
                "minimum_required_emergencies": MINIMUM_DISTINCT_EMERGENCIES_THRESHOLD,
                "blocking_reasons": blocking_reasons,
                "recommendation": (
                    "Proceed with feature pipeline and model training."
                    if is_ready_for_training
                    else "Maintain deterministic baseline ranker; gather genuine operational response outcomes via active interaction ledger."
                ),
            },
        }


ml_audit_service = MLAuditService()
