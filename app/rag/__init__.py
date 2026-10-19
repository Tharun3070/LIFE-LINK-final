"""LifeLink Clinical Retrieval-Augmented Generation (RAG) Subsystem."""
from app.rag.document_store import ClinicalDocument, TRUSTED_CLINICAL_DOCUMENTS
from app.rag.vector_store import InMemoryVectorStore, DocumentChunk
from app.rag.service import (
    ClinicalRAGService,
    ClinicalCitation,
    RAGResponse,
    clinical_rag_service,
)

__all__ = [
    "ClinicalDocument",
    "TRUSTED_CLINICAL_DOCUMENTS",
    "InMemoryVectorStore",
    "DocumentChunk",
    "ClinicalRAGService",
    "ClinicalCitation",
    "RAGResponse",
    "clinical_rag_service",
]
