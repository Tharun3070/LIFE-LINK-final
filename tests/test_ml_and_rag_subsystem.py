"""Tests for Priority 5: ML Data Readiness Gate, Clinical Matching Safety, and RAG Grounded Retrieval."""
import pytest
from app.models.emergency import Emergency
from app.models.donor import Donor
from app.models.hospital import Hospital
from app.services.ml_ranking_service import ml_ranking_service
from app.rag.service import clinical_rag_service
from app.rag.document_store import ClinicalDocument, TRUSTED_CLINICAL_DOCUMENTS


def test_ml_data_readiness_gate_blocks_training(db, client, doctor_token):
    """The ML training gate evaluates outcome counts and blocks training when < 2,500 production outcomes exist."""
    readiness = ml_ranking_service.assess_training_readiness(db)
    assert readiness["is_ready_for_training"] is False
    assert readiness["training_status"] == "BLOCKED_BY_DATA_GATE"
    assert readiness["eligible_production_outcomes"] < 2500
    assert len(readiness["blocking_reasons"]) > 0

    # Verify API endpoint reflects the blocked gate
    resp = client.get(
        "/api/v1/ml/readiness",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["training_status"] == "BLOCKED_BY_DATA_GATE"
    assert data["is_ready_for_training"] is False


@pytest.mark.asyncio
async def test_ml_donor_ranking_clinical_precedence_and_fallback(db):
    """Hard ABO compatibility cannot be overridden by ML; incompatible and synthetic donors are excluded."""
    hospital = db.query(Hospital).first()
    assert hospital is not None

    # Create test emergency for O- recipient
    emg = Emergency(
        id="EMG-ML-TEST-001",
        type="blood",
        priority="critical",
        status="created",
        hospital_id=hospital.id,
        hospital_name=hospital.name,
        created_at="2026-10-18T10:00:00Z",
        updated_at="2026-10-18T10:00:00Z",
        description="Trauma emergency needing O- blood",
        blood_group="O-",
        units_required=2,
    )
    db.add(emg)

    # Donor 1: O- (compatible, genuine)
    d1 = Donor(
        id="D-COMPAT-GENUINE-01",
        blood_group="O-",
        lat=12.9716,
        lng=77.5946,
        distance_km=4.5,
        eta_minutes=15,
        last_donation_days=95,
        status="available",
        eligibility="eligible",
        is_synthetic=False,
    )

    # Donor 2: B+ (incompatible for O- recipient)
    d2 = Donor(
        id="D-INCOMPAT-GENUINE-02",
        blood_group="B+",
        lat=12.9716,
        lng=77.5946,
        distance_km=2.0,
        eta_minutes=8,
        last_donation_days=120,
        status="available",
        eligibility="eligible",
        is_synthetic=False,
    )

    # Donor 3: O- (compatible, but synthetic benchmark profile)
    d3 = Donor(
        id="D-COMPAT-SYNTHETIC-03",
        blood_group="O-",
        lat=12.9716,
        lng=77.5946,
        distance_km=1.0,
        eta_minutes=5,
        last_donation_days=100,
        status="available",
        eligibility="eligible",
        is_synthetic=True,
    )

    db.add_all([d1, d2, d3])
    db.commit()

    # Rank candidate donors
    results = await ml_ranking_service.rank_donors(
        emergency_id=emg.id,
        candidate_donor_ids=[d1.id, d2.id, d3.id],
        db=db,
    )

    # Verify results:
    # 1. d1 (genuine O-) is included
    # 2. d2 (incompatible B+) is EXCLUDED
    # 3. d3 (synthetic benchmark) is EXCLUDED
    donor_ids = [r["donor_id"] for r in results]
    assert d1.id in donor_ids
    assert d2.id not in donor_ids
    assert d3.id not in donor_ids

    assert results[0]["ranking_method"] == "deterministic_clinical_fallback"
    assert results[0]["ml_active"] is False


def test_rag_document_checksum_and_provenance():
    """Documents in the clinical store compute deterministic SHA-256 checksums."""
    doc = TRUSTED_CLINICAL_DOCUMENTS[0]
    checksum = doc.compute_checksum()
    assert len(checksum) == 64
    assert checksum == doc.compute_checksum()

    # Tampering changes checksum
    tampered_doc = ClinicalDocument(
        doc_id="DOC-TAMPERED",
        title="Tampered Doc",
        issuing_organization="Unknown",
        source_url="http://example.com",
        publication_date="2026-01-01",
        domain="blood_transfusion",
        version="v1.0",
        content="Tampered content",
    )
    assert tampered_doc.compute_checksum() != checksum


def test_rag_grounded_query_with_citations(client, doctor_token):
    """Clinical RAG returns evidence-grounded answers with citations for valid clinical queries."""
    # Query organ viability CIT threshold
    res = clinical_rag_service.query_clinical_guidance(
        query="What is the maximum cold ischemic time for heart transplantation?",
        domain="organ_viability",
    )
    assert res.insufficient_evidence is False
    assert res.retrieval_status == "EVIDENCE_GROUNDED"
    assert len(res.citations) > 0
    assert "heart" in res.answer.lower()
    assert "4 to 6 hours" in res.answer or "4" in res.answer
    assert any("NOTTO" in c.issuing_organization for c in res.citations)

    # Test via API
    api_resp = client.post(
        "/api/v1/clinical-guidance/query",
        json={"query": "cold ischemic time heart transplant", "domain": "organ_viability"},
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert api_resp.status_code == 200
    api_data = api_resp.json()
    assert api_data["insufficient_evidence"] is False
    assert len(api_data["citations"]) > 0


def test_rag_medical_safety_abstention_on_irrelevant_query():
    """RAG abstains and refuses to hallucinate when evidence is insufficient or irrelevant."""
    res = clinical_rag_service.query_clinical_guidance(
        query="How do I change the oil filter on a 2018 Honda Civic motorcycle?",
    )
    assert res.insufficient_evidence is True
    assert res.retrieval_status == "ABSTAINED_INSUFFICIENT_EVIDENCE"
    assert len(res.citations) == 0
    assert "insufficient evidence" in res.answer.lower()


def test_clinical_documents_registry_endpoint(client, doctor_token):
    """The document registry endpoint returns provenance metadata for all ingested clinical guidance."""
    resp = client.get(
        "/api/v1/clinical-guidance/documents",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) >= 3
    doc_ids = [d["docId"] for d in docs]
    assert "DOC-WHO-BTC-2021" in doc_ids
    assert "DOC-NOTTO-ORGAN-VIABILITY-2023" in doc_ids
    assert all("checksum" in d and len(d["checksum"]) == 64 for d in docs)
