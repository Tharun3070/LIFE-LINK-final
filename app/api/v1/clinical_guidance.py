"""Clinical Guidance RAG and Machine Learning Readiness API Endpoints."""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.rag.service import clinical_rag_service, RAGResponse
from app.rag.document_store import TRUSTED_CLINICAL_DOCUMENTS
from app.services.ml_ranking_service import ml_ranking_service
from app.core.dependencies import get_current_user
from app.schemas.auth import UserProfileSchema
from app.schemas.llm import EmergencyIntentRequest, EmergencyIntentResult, GroundedExplanationRequest, GroundedExplanationResponse
from app.ai.llm_service import llm_service

router = APIRouter(tags=["Clinical Intelligence & Knowledge Retrieval"])

CLINICAL_COORDINATION_ROLES = {"doctor", "hospital_staff", "admin", "transplant_coordinator"}


class ClinicalQueryRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Clinical query regarding blood cold chain, organ ischemic time, or transfusion rules")
    domain: Optional[str] = Field(None, description="Clinical domain filter (e.g. blood_transfusion, organ_viability)")


@router.post(
    "/clinical-guidance/query",
    response_model=RAGResponse,
    summary="Query Grounded Clinical Guidance (RAG)",
    description="Retrieves evidence-grounded clinical knowledge with source citations from WHO, AABB, and NOTTO guidelines.",
)
def query_clinical_guidance(
    body: ClinicalQueryRequest,
    current_user: UserProfileSchema = Depends(get_current_user),
):
    return clinical_rag_service.query_clinical_guidance(
        query=body.query,
        domain=body.domain,
        user_role=current_user.role,
    )


@router.get(
    "/clinical-guidance/documents",
    summary="List Trusted Clinical Documents",
    description="Returns registry of trusted clinical documents with issuing organizations, publication dates, and provenance.",
)
def list_trusted_documents(
    current_user: UserProfileSchema = Depends(get_current_user),
):
    return [
        {
            "docId": doc.doc_id,
            "title": doc.title,
            "issuingOrganization": doc.issuing_organization,
            "sourceUrl": doc.source_url,
            "publicationDate": doc.publication_date,
            "domain": doc.domain,
            "version": doc.version,
            "checksum": doc.compute_checksum(),
        }
        for doc in TRUSTED_CLINICAL_DOCUMENTS
    ]


@router.get(
    "/ml/readiness",
    summary="ML Training Readiness & Gate Evaluation",
    description="Audits genuine production outcomes against the project's 2,500-sample / 250-emergency readiness gate.",
)
def get_ml_readiness(
    db: Session = Depends(get_db),
    current_user: UserProfileSchema = Depends(get_current_user),
):
    return ml_ranking_service.assess_training_readiness(db)


@router.post(
    "/clinical-guidance/parse-intent",
    response_model=EmergencyIntentResult,
    summary="Parse Emergency Intent via LLM",
    description="Extracts structured emergency attributes (blood group, units, urgency, facility) from clinical text with safe fallback.",
)
async def parse_emergency_intent(
    body: EmergencyIntentRequest,
    current_user: UserProfileSchema = Depends(get_current_user),
):
    return await llm_service.parse_emergency_intent(body.text)


@router.post(
    "/clinical-guidance/explain-match",
    response_model=GroundedExplanationResponse,
    summary="Generate Grounded Clinical Explanation",
    description="Synthesizes a grounded, privacy-preserving explanation of matching results and clinical evidence.",
)
async def explain_clinical_match(
    body: GroundedExplanationRequest,
    current_user: UserProfileSchema = Depends(get_current_user),
):
    clean_role = (current_user.role or "").lower()
    if clean_role not in CLINICAL_COORDINATION_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Access denied: Clinical matching explanation requires an authorized clinical or hospital coordination role.",
        )

    retrieved_docs = []
    if body.include_clinical_guidelines:
        bg = body.sanitized_context.get("requested_blood_group", "blood")
        comp = body.sanitized_context.get("requested_component", "component")
        query_text = body.query or f"Clinical protocols and storage guidelines for {bg} {comp} transfusion"
        hospital_id = current_user.hospitalId or "default_facility"
        try:
            retrieved_docs = await clinical_rag_service.retrieve_authorized_context(
                query=query_text,
                user_role=current_user.role,
                hospital_id=hospital_id,
            )
        except Exception:
            retrieved_docs = []

    result = await llm_service.generate_grounded_answer(
        sanitized_context=body.sanitized_context,
        query=body.query,
        retrieved_documents=retrieved_docs,
    )
    return GroundedExplanationResponse(**result)

