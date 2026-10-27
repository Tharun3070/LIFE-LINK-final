"""Tests for ML Training Pipeline, Grouped Splitting, and XGBoost Inference Fallback."""
import pytest
from unittest.mock import MagicMock
from app.services.ml_training_pipeline import (
    MLDataPipeline,
    XGBoostRankingPipeline,
    FEATURE_NAMES,
)
from app.services.ml_ranking_service import MLDonorRankingService
from app.models.donor import Donor
from app.models.emergency import Emergency


def test_feature_names_schema():
    """Validates that ML feature schema contains only pre-dispatch attributes (zero target leakage)."""
    assert "distance_km" in FEATURE_NAMES
    assert "eta_minutes" in FEATURE_NAMES
    assert "total_previous_donations" in FEATURE_NAMES
    assert "days_since_last_donation" in FEATURE_NAMES
    # Leakage checks: post-dispatch and resolution metrics must NOT be in feature columns
    assert "units_donated" not in FEATURE_NAMES
    assert "response_latency_seconds" not in FEATURE_NAMES
    assert "completed_at" not in FEATURE_NAMES


def test_grouped_splits_prevents_emergency_leakage():
    """Guarantees that interaction records belonging to the same emergency never cross train/val/test splits."""
    dummy_records = [
        {"emergency_id": "emg_1", "interaction_id": "i1", "label": 1},
        {"emergency_id": "emg_1", "interaction_id": "i2", "label": 0},
        {"emergency_id": "emg_2", "interaction_id": "i3", "label": 1},
        {"emergency_id": "emg_2", "interaction_id": "i4", "label": 0},
        {"emergency_id": "emg_3", "interaction_id": "i5", "label": 1},
        {"emergency_id": "emg_4", "interaction_id": "i6", "label": 0},
        {"emergency_id": "emg_5", "interaction_id": "i7", "label": 1},
    ]

    train, val, test = MLDataPipeline.create_grouped_splits(dummy_records, train_ratio=0.6, val_ratio=0.2)

    train_emgs = {r["emergency_id"] for r in train}
    val_emgs = {r["emergency_id"] for r in val}
    test_emgs = {r["emergency_id"] for r in test}

    # Strict partition verification
    assert train_emgs.isdisjoint(val_emgs)
    assert train_emgs.isdisjoint(test_emgs)
    assert val_emgs.isdisjoint(test_emgs)


def test_training_pipeline_blocks_when_insufficient_records(db):
    """Refuses training when genuine production interactions are below the 2,500 threshold."""
    res = XGBoostRankingPipeline.train_and_persist(db=db, force=False)
    assert res["status"] == "BLOCKED_BY_DATA_GATE"
    assert "Insufficient genuine production data" in res["reason"]


def test_check_xgboost_availability():
    """Detects library availability without throwing unhandled exceptions."""
    is_avail = XGBoostRankingPipeline.check_xgboost_available()
    assert isinstance(is_avail, bool)


@pytest.mark.asyncio
async def test_ml_ranking_service_deterministic_fallback(db):
    """When data gate is not met, ranking strictly falls back to deterministic clinical heuristic."""
    service = MLDonorRankingService()
    donor = db.query(Donor).filter(Donor.status == "available").first() or db.query(Donor).first()
    emg = db.query(Emergency).first()

    if donor and emg:
        res = await service.rank_donors(emergency_id=emg.id, candidate_donor_ids=[donor.id], db=db)
        if res:
            first = res[0]
            assert first["ranking_method"] == "deterministic_clinical_fallback"
            assert first["ml_active"] is False
            assert "data_gate_status" in first


@pytest.mark.asyncio
async def test_ml_ranking_service_with_mocked_model(db, monkeypatch):
    """Verifies that if model is loaded and data gate is forced ready, XGBoost scoring is applied."""
    service = MLDonorRankingService()

    # Mock model
    mock_model = MagicMock()
    mock_model.predict_proba.return_value = [[0.12, 0.88]]  # 88% probability
    service._loaded_model = mock_model

    # Mock readiness to simulate gate passed
    monkeypatch.setattr(
        service,
        "assess_training_readiness",
        lambda db: {"is_ready_for_training": True, "training_status": "READY"},
    )

    donor = db.query(Donor).filter(Donor.status == "available").first() or db.query(Donor).first()
    emg = db.query(Emergency).first()

    if donor and emg:
        res = await service.rank_donors(emergency_id=emg.id, candidate_donor_ids=[donor.id], db=db)
        if res:
            first = res[0]
            assert first["ranking_method"] == "xgboost_supervised_model"
            assert first["ml_active"] is True
            assert first["score"] == 88.0
            assert "88.0%" in first["explainability"]["ml_predicted_response_probability"]
