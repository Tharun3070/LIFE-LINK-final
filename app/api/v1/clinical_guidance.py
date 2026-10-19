"""Clinical Guidance RAG and Machine Learning Readiness API Endpoints."""
from typing import Optional, List
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.rag.service import clinical_rag_service, RAGResponse
from app.rag.document_store import TRUSTED_CLINICAL_DOCUMENTS
from app.services.ml_ranking_service import ml_ranking_service
from app.core.dependencies import get_current_user
from app.schemas.auth import UserProfileSchema

router = APIRouter(tags=["Clinical Intelligence & Knowledge Retrieval"])


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
