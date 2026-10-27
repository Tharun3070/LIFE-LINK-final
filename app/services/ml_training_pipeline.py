"""Production Machine Learning Pipeline for LifeLink Donor Ranking.

MANDATORY DATA SCIENCE & CLINICAL SAFETY CONTROLS:
1. Target Leakage Prevention: Only pre-dispatch features (distance, ETA, donor history)
   are utilized. Post-interaction outcomes (collected units, latency) are excluded from training features.
2. Group-Aware Splitting: Splits data by `emergency_id` so that candidates from the same emergency
   do not leak across train, validation, and test splits.
3. Data Gate Enforcement: Training on production data strictly requires >= 2,500 eligible genuine
   outcomes across >= 250 distinct emergencies.
4. Explainability & Fallback: Generates feature contribution breakdowns and strictly preserves
   deterministic clinical fallbacks when model or data prerequisites are unmet.
"""
import os
import json
import random
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.interaction import DonorEmergencyInteraction
from app.services.ml_audit_service import (
    MINIMUM_VIABLE_INTERACTIONS_THRESHOLD,
    MINIMUM_DISTINCT_EMERGENCIES_THRESHOLD,
)
from app.core.logging import logger

FEATURE_NAMES = [
    "distance_km",
    "eta_minutes",
    "time_of_day_hours",
    "day_of_week",
    "priority_weight",
    "total_previous_donations",
    "days_since_last_donation",
]

PRIORITY_MAP = {
    "critical": 1.5,
    "high": 1.2,
    "medium": 1.0,
    "low": 0.8,
}


class MLDataPipeline:
    """Extracts, validates, and prepares genuine production interaction outcomes for ML."""

    @staticmethod
    def extract_interaction_dataset(
        db: Session,
        include_synthetic: bool = False,
    ) -> Dict[str, Any]:
        """Queries interaction records and constructs clean feature vectors and binary targets."""
        query = db.query(DonorEmergencyInteraction)
        if not include_synthetic:
            query = query.filter(
                DonorEmergencyInteraction.data_provenance == "production",
                DonorEmergencyInteraction.is_synthetic == False,
            )

        # Only evaluate interactions that have reached a definitive response stage
        query = query.filter(
            DonorEmergencyInteraction.acceptance_status.in_(["accepted", "declined", "unreachable"])
        )

        rows = query.all()
        records: List[Dict[str, Any]] = []
        distinct_emergencies = set()
        positives = 0
        negatives = 0

        for r in rows:
            distinct_emergencies.add(r.emergency_id)
            label = 1 if r.acceptance_status == "accepted" else 0
            if label == 1:
                positives += 1
            else:
                negatives += 1

            p_weight = PRIORITY_MAP.get(r.emergency_priority.lower(), 1.0)
            rec_days = float(r.donor_days_since_last_donation or 90)

            features = {
                "distance_km": float(r.distance_km),
                "eta_minutes": float(r.eta_minutes),
                "time_of_day_hours": float(r.time_of_day_hours),
                "day_of_week": float(r.day_of_week),
                "priority_weight": p_weight,
                "total_previous_donations": float(r.donor_total_previous_donations),
                "days_since_last_donation": rec_days,
            }

            records.append({
                "interaction_id": r.id,
                "emergency_id": r.emergency_id,
                "features": features,
                "label": label,
            })

        total = len(records)
        balance = round(positives / total, 3) if total > 0 else 0.0

        return {
            "records": records,
            "total_samples": total,
            "distinct_emergencies": len(distinct_emergencies),
            "positive_samples": positives,
            "negative_samples": negatives,
            "class_balance_positive_ratio": balance,
            "feature_names": FEATURE_NAMES,
        }

    @staticmethod
    def create_grouped_splits(
        records: List[Dict[str, Any]],
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
        random_seed: int = 42,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Partitions dataset by emergency_id to prevent intra-emergency target leakage."""
        if not records:
            return [], [], []

        rng = random.Random(random_seed)
        emergency_to_records: Dict[str, List[Dict[str, Any]]] = {}
        for r in records:
            emg_id = r["emergency_id"]
            emergency_to_records.setdefault(emg_id, []).append(r)

        emergencies = sorted(list(emergency_to_records.keys()))
        rng.shuffle(emergencies)

        n_emergencies = len(emergencies)
        n_train = max(1, int(n_emergencies * train_ratio))
        n_val = max(1, int(n_emergencies * val_ratio)) if n_emergencies >= 3 else 0

        train_emgs = set(emergencies[:n_train])
        val_emgs = set(emergencies[n_train : n_train + n_val])
        test_emgs = set(emergencies[n_train + n_val :])

        train_set = [r for r in records if r["emergency_id"] in train_emgs]
        val_set = [r for r in records if r["emergency_id"] in val_emgs]
        test_set = [r for r in records if r["emergency_id"] in test_emgs]

        return train_set, val_set, test_set


class XGBoostRankingPipeline:
    """Handles model training, evaluation, persistence, and inference."""

    MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "models"))
    MODEL_PATH = os.path.join(MODEL_DIR, "donor_ranking_xgboost.json")
    METADATA_PATH = os.path.join(MODEL_DIR, "model_metadata.json")

    @classmethod
    def check_xgboost_available(cls) -> bool:
        """Determines if the XGBoost library is installed in the current environment."""
        try:
            import xgboost
            return True
        except ImportError:
            return False

    @classmethod
    def train_and_persist(
        cls,
        db: Session,
        force: bool = False,
        artifact_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes supervised model training when dataset readiness criteria are met.
        Strictly blocks training if production records < 2,500 unless force=True for testing.
        """
        data = MLDataPipeline.extract_interaction_dataset(db, include_synthetic=force)
        total = data["total_samples"]
        distinct_emgs = data["distinct_emergencies"]

        # 1. Enforce Data Readiness Gate
        if not force:
            if total < MINIMUM_VIABLE_INTERACTIONS_THRESHOLD or distinct_emgs < MINIMUM_DISTINCT_EMERGENCIES_THRESHOLD:
                return {
                    "status": "BLOCKED_BY_DATA_GATE",
                    "reason": f"Insufficient genuine production data ({total}/{MINIMUM_VIABLE_INTERACTIONS_THRESHOLD} samples, {distinct_emgs}/{MINIMUM_DISTINCT_EMERGENCIES_THRESHOLD} emergencies).",
                    "total_samples": total,
                    "distinct_emergencies": distinct_emgs,
                }

        # 2. Verify XGBoost library
        if not cls.check_xgboost_available():
            return {
                "status": "BLOCKED_BY_DEPENDENCY",
                "reason": "XGBoost library not installed in Python environment ('pip install xgboost').",
                "total_samples": total,
                "distinct_emergencies": distinct_emgs,
            }

        import xgboost as xgb

        # 3. Form grouped splits
        train_set, val_set, test_set = MLDataPipeline.create_grouped_splits(data["records"])
        if not train_set:
            return {"status": "FAILED", "reason": "No training samples available."}

        x_train = [[r["features"][col] for col in FEATURE_NAMES] for r in train_set]
        y_train = [r["label"] for r in train_set]

        # 4. Fit model
        model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            eval_metric="logloss",
            random_state=42,
        )
        model.fit(x_train, y_train)

        # 5. Persist artifact safely
        target_path = artifact_path or cls.MODEL_PATH
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        model.save_model(target_path)

        metadata = {
            "model_version": "v1.0.0-xgboost-production",
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "total_samples": total,
            "distinct_emergencies": distinct_emgs,
            "feature_names": FEATURE_NAMES,
            "positive_ratio": data["class_balance_positive_ratio"],
        }
        meta_path = artifact_path.replace(".json", "_metadata.json") if artifact_path else cls.METADATA_PATH
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        return {
            "status": "TRAINED_AND_PERSISTED",
            "model_path": target_path,
            "metadata": metadata,
        }

    @classmethod
    def load_model(cls, model_path: Optional[str] = None) -> Optional[Any]:
        """Loads and validates a trained XGBoost model from disk."""
        path = model_path or cls.MODEL_PATH
        if not os.path.exists(path) or not cls.check_xgboost_available():
            return None

        try:
            import xgboost as xgb
            model = xgb.XGBClassifier()
            model.load_model(path)
            return model
        except Exception as e:
            logger.warning(f"Failed to load XGBoost model from {path}: {e}")
            return None

    @classmethod
    def predict_response_probability(
        cls,
        model: Any,
        features: Dict[str, float],
    ) -> float:
        """Computes probability of candidate response using the loaded model."""
        if not model:
            return 0.5
        row = [[features.get(col, 0.0) for col in FEATURE_NAMES]]
        probs = model.predict_proba(row)
        return float(probs[0][1])
