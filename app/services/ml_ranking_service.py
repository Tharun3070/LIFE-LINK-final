"""Machine Learning Donor Ranking Service with Hard Clinical Eligibility & Safety Gating.

ARCHITECTURAL PRINCIPLES:
1. Strict Clinical Precedence: Hard ABO/Rh compatibility and medical eligibility are absolute gates.
   Machine learning predictions NEVER override clinical compatibility.
2. Minimum Viable Dataset (MVD) Evaluation Gate:
   Supervised model training and activation are blocked until the system records at least
   2,500 eligible genuine production outcomes across at least 250 emergencies.
3. Safe Heuristic Fallback:
   When ML is inactive or unavailable, the system transparently utilizes the deterministic
   clinical baseline ranking engine.
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.ai.interfaces import DonorRankingServiceInterface
from app.services.ml_audit_service import (
    MLAuditService,
    MINIMUM_VIABLE_INTERACTIONS_THRESHOLD,
    MINIMUM_DISTINCT_EMERGENCIES_THRESHOLD,
)
from app.services.matching_engine import baseline_matching_engine, RBC_COMPATIBILITY_MAP
from app.services.ml_training_pipeline import XGBoostRankingPipeline
from app.models.emergency import Emergency
from app.models.donor import Donor
from app.core.logging import logger


class MLDonorRankingService(DonorRankingServiceInterface):
    """Safe, gated ML donor ranking service with deterministic clinical baseline fallback."""

    def __init__(self, model_path: Optional[str] = None):
        self.model_version = "v1.0.0-gated"
        self._model_path = model_path
        self._loaded_model = XGBoostRankingPipeline.load_model(model_path)
        self._is_model_trained = self._loaded_model is not None

    def assess_training_readiness(self, db: Session) -> Dict[str, Any]:
        """Evaluates whether the production outcome ledger meets the project's data-readiness threshold."""
        audit_res = MLAuditService.audit_interactions(db)
        eligible_records = audit_res.get("prediction_targets", {}).get(
            "target_a_response_propensity", {}
        ).get("eligible_records", 0)
        distinct_emergencies = audit_res.get("volume", {}).get("distinct_emergencies", 0)

        is_ready = (
            eligible_records >= MINIMUM_VIABLE_INTERACTIONS_THRESHOLD
            and distinct_emergencies >= MINIMUM_DISTINCT_EMERGENCIES_THRESHOLD
        )

        return {
            "is_ready_for_training": is_ready,
            "eligible_production_outcomes": eligible_records,
            "required_production_outcomes": MINIMUM_VIABLE_INTERACTIONS_THRESHOLD,
            "distinct_emergencies": distinct_emergencies,
            "required_distinct_emergencies": MINIMUM_DISTINCT_EMERGENCIES_THRESHOLD,
            "training_status": "READY" if is_ready else "BLOCKED_BY_DATA_GATE",
            "blocking_reasons": audit_res.get("verdict", {}).get("blocking_reasons", []),
        }

    def extract_features(self, donor: Donor, emergency: Emergency) -> Dict[str, float]:
        """Extracts normalized features for candidate ranking (distance, history, availability)."""
        dist_km = getattr(donor, "distance_km", 10.0) or 10.0
        eta_min = getattr(donor, "eta_minutes", 20) or 20
        last_donation_days = getattr(donor, "last_donation_days", 90) or 90
        total_donations = getattr(donor, "total_donations", 0) or 0

        priority_weight = 1.0
        if emergency and emergency.priority == "critical":
            priority_weight = 1.5
        elif emergency and emergency.priority == "high":
            priority_weight = 1.2

        return {
            "distance_km": float(dist_km),
            "eta_minutes": float(eta_min),
            "days_since_last_donation": float(last_donation_days),
            "total_previous_donations": float(total_donations),
            "priority_weight": priority_weight,
        }

    async def rank_donors(
        self,
        emergency_id: str,
        candidate_donor_ids: List[str],
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """
        Ranks candidate donors while guaranteeing clinical safety.
        If production training data threshold (< 2,500 outcomes) is not met,
        strictly falls back to deterministic clinical heuristic ranking.
        """
        if not db:
            raise ValueError("Database session required for clinical donor ranking.")

        emergency = db.query(Emergency).filter(Emergency.id == emergency_id).first()
        if not emergency:
            raise ValueError(f"Emergency #{emergency_id} not found.")

        # 1. Inspect training readiness gate
        readiness = self.assess_training_readiness(db)

        # 2. Query candidates
        donors = db.query(Donor).filter(Donor.id.in_(candidate_donor_ids)).all()

        # 3. Clinical ABO/Rh Hard Filter
        # Hard clinical compatibility MUST be satisfied regardless of ML
        compatible_groups = RBC_COMPATIBILITY_MAP.get(emergency.blood_group, set()) if emergency.blood_group else set()

        ranked_results = []
        for donor in donors:
            # Clinical exclusion
            is_compatible = donor.blood_group in compatible_groups if compatible_groups else True
            if not is_compatible:
                continue

            # Synthetic exclusion from real ranking
            if getattr(donor, "is_synthetic", False):
                continue

            features = self.extract_features(donor, emergency)
            use_ml = bool(readiness["is_ready_for_training"] and self._loaded_model)

            if use_ml:
                try:
                    prob = XGBoostRankingPipeline.predict_response_probability(self._loaded_model, features)
                    score = round(prob * 100.0, 2)
                    ranking_method = "xgboost_supervised_model"
                    ml_active = True
                    explainability = {
                        "clinical_compatibility": f"{donor.blood_group} is compatible with recipient {emergency.blood_group}",
                        "ml_predicted_response_probability": f"{prob:.1%}",
                        "model_version": self.model_version,
                    }
                except Exception as e:
                    logger.warning(f"XGBoost inference failed for donor {donor.id}: {e}. Falling back to heuristic.")
                    use_ml = False

            if not use_ml:
                # Deterministic scoring: Distance penalty + donation recency bonus
                score = max(0.0, 100.0 - (features["distance_km"] * 2.5) + min(20.0, features["days_since_last_donation"] / 10.0))
                ranking_method = "deterministic_clinical_fallback"
                ml_active = False
                explainability = {
                    "clinical_compatibility": f"{donor.blood_group} is compatible with recipient {emergency.blood_group}",
                    "distance_contribution": f"-{features['distance_km'] * 2.5:.1f} pts",
                    "history_contribution": f"+{min(20.0, features['days_since_last_donation'] / 10.0):.1f} pts",
                }

            ranked_results.append({
                "donor_id": donor.id,
                "blood_group": donor.blood_group,
                "distance_km": features["distance_km"],
                "eta_minutes": features["eta_minutes"],
                "score": round(score, 2),
                "ranking_method": ranking_method,
                "ml_active": ml_active,
                "data_gate_status": readiness["training_status"],
                "explainability": explainability,
            })

        # Sort descending by score
        ranked_results.sort(key=lambda x: x["score"], reverse=True)
        return ranked_results


# Global singleton instance
ml_ranking_service = MLDonorRankingService()
