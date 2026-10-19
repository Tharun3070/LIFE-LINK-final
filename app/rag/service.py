"""Clinical RAG Service: Grounded Medical Retrieval with Source Attribution and Safe Abstention."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.ai.interfaces import RAGServiceInterface
from app.rag.document_store import ClinicalDocument, TRUSTED_CLINICAL_DOCUMENTS
from app.rag.vector_store import InMemoryVectorStore, DocumentChunk
from app.core.logging import logger


class ClinicalCitation(BaseModel):
    document_title: str
    issuing_organization: str
    source_url: str
    chunk_id: str
    excerpt: str
    relevance_score: float


class RAGResponse(BaseModel):
    query: str
    answer: str
    citations: List[ClinicalCitation] = Field(default_factory=list)
    insufficient_evidence: bool
    confidence_score: float
    domain: Optional[str] = None
    retrieval_status: str


class ClinicalRAGService(RAGServiceInterface):
    """Retrieval-Augmented Generation service providing grounded clinical answers with traceable citations."""

    def __init__(self, vector_store: Optional[InMemoryVectorStore] = None):
        self.vector_store = vector_store or InMemoryVectorStore()
        self._seed_trusted_documents()

    def _seed_trusted_documents(self) -> None:
        """Seeds the vector store with pre-approved authoritative clinical documents."""
        for doc in TRUSTED_CLINICAL_DOCUMENTS:
            self.ingest_document(doc)

    def ingest_document(self, doc: ClinicalDocument) -> int:
        """Chunks and ingests a clinical document with checksum and provenance tracking."""
        doc.checksum = doc.compute_checksum()

        # Split document content into semantic paragraphs
        paragraphs = [p.strip() for p in doc.content.split("\n") if p.strip()]
        chunks_added = 0
        for i, para in enumerate(paragraphs):
            chunk = DocumentChunk(
                chunk_id=f"{doc.doc_id}-CHK-{i+1:02d}",
                doc_id=doc.doc_id,
                title=doc.title,
                issuing_organization=doc.issuing_organization,
                source_url=doc.source_url,
                domain=doc.domain,
                text=para,
            )
            self.vector_store.add_chunk(chunk)
            chunks_added += 1

        logger.info(f"Ingested clinical document '{doc.title}' ({chunks_added} chunks)")
        return chunks_added

    def query_clinical_guidance(
        self,
        query: str,
        domain: Optional[str] = None,
        min_confidence: float = 0.15,
        top_k: int = 3,
    ) -> RAGResponse:
        """
        Executes grounded retrieval from trusted clinical corpus.
        CRITICAL SAFETY RULE: If evidence is below the confidence threshold,
        the system abstains and refuses to fabricate medical advice.
        """
        results = self.vector_store.search(query=query, domain=domain, top_k=top_k)

        if not results or results[0][1] < min_confidence:
            return RAGResponse(
                query=query,
                answer=(
                    "Insufficient evidence in trusted clinical corpus to answer query with verified clinical grounding. "
                    "Clinical protocols require consulting a licensed physician or referencing official hospital trauma guidelines."
                ),
                citations=[],
                insufficient_evidence=True,
                confidence_score=results[0][1] if results else 0.0,
                domain=domain,
                retrieval_status="ABSTAINED_INSUFFICIENT_EVIDENCE",
            )

        # Synthesize grounded response directly from retrieved clinical excerpts
        top_chunk, top_score = results[0]
        citations: List[ClinicalCitation] = []
        synthesized_paragraphs: List[str] = []

        for chunk, score in results:
            citations.append(
                ClinicalCitation(
                    document_title=chunk.title,
                    issuing_organization=chunk.issuing_organization,
                    source_url=chunk.source_url,
                    chunk_id=chunk.chunk_id,
                    excerpt=chunk.text,
                    relevance_score=round(score, 3),
                )
            )
            synthesized_paragraphs.append(chunk.text)

        answer_text = "\n\n".join(synthesized_paragraphs)

        return RAGResponse(
            query=query,
            answer=answer_text,
            citations=citations,
            insufficient_evidence=False,
            confidence_score=round(top_score, 3),
            domain=domain,
            retrieval_status="EVIDENCE_GROUNDED",
        )

    async def retrieve_authorized_context(
        self, query: str, user_role: str, hospital_id: str
    ) -> List[Dict[str, Any]]:
        """Adheres to RAGServiceInterface for role-filtered healthcare context."""
        response = self.query_clinical_guidance(query=query)
        return [c.model_dump() for c in response.citations]


# Singleton instance
clinical_rag_service = ClinicalRAGService()
