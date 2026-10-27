"""
LifeLink Clinical Coordination Service.
Orchestrates the complete, privacy-preserving healthcare emergency workflow:
1. Deterministic database-driven donor matching.
2. Clinical RAG evidence retrieval.
3. Privacy sanitization & data minimization.
4. Grounded LLM clinical explanation generation.
5. Strict output validation.
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models.donor import Donor
from app.services.matching_engine import baseline_matching_engine, CandidateEvaluation
from app.services.privacy_service import privacy_service
from app.rag.service import clinical_rag_service
from app.ai.llm_service import llm_service
from app.core.logging import logger


class ClinicalCoordinationService:
    """
    Coordinates matching, RAG, and LLM while maintaining strict separation of concerns.
    Deterministic database matches remain authoritative and are never overridden by the LLM.
    """

    async def coordinate_emergency_match(
        self,
        recipient_blood_group: str,
        component: str = "red_blood_cells",
        location_name: Optional[str] = None,
        hospital_lat: Optional[float] = None,
        hospital_lng: Optional[float] = None,
        units_requested: Optional[int] = None,
        query: Optional[str] = None,
        user_role: Optional[str] = None,
        hospital_id: Optional[str] = None,
        db: Optional[Session] = None,
        provided_donors: Optional[List[Donor]] = None,
    ) -> Dict[str, Any]:
        """
        Executes the end-to-end LifeLink Emergency Workflow:
        Database Query -> Deterministic Matching -> Privacy Minimization -> Grounded AI Explanation.
        """
        # 1. Fetch Donors from Authoritative Relational DB (or use provided donors for test fixtures)
        if provided_donors is not None:
            all_donors = provided_donors
        elif db is not None:
            all_donors = db.query(Donor).all()
        else:
            all_donors = []

        # 2. Deterministic Candidate Matching (Component-Specific ABO/Rh and Eligibility Filtering)
        eligible_candidates, excluded_candidates = baseline_matching_engine.evaluate_candidates(
            donors=all_donors,
            recipient_blood_group=recipient_blood_group,
            hospital_lat=hospital_lat,
            hospital_lng=hospital_lng,
            component=component,
        )

        # 3. Optional Clinical Guidance Retrieval (Role-Filtered RAG)
        retrieved_docs: List[Dict[str, Any]] = []
        rag_query = query or f"Clinical protocols for {recipient_blood_group} {component} emergency transfusion and cold storage"
        try:
            retrieved_docs = await clinical_rag_service.retrieve_authorized_context(
                query=rag_query,
                user_role=user_role or "doctor",
                hospital_id=hospital_id or "default_facility",
            )
        except Exception as e:
            logger.warning(f"RAG retrieval skipped or failed: {type(e).__name__}")

        # 4. Privacy Sanitization & Data Minimization (Zero PII sent to LLM)
        sanitized_context = privacy_service.build_sanitized_matching_context(
            recipient_blood_group=recipient_blood_group,
            component=component,
            location_name=location_name or "Emergency Regional Hospital",
            eligible_candidates=eligible_candidates,
            excluded_candidates=excluded_candidates,
            units_requested=units_requested,
            clinical_evidence=retrieved_docs,
        )

        # 5. Grounded LLM Explanation Generation with Automatic Fallback
        grounded_explanation = await llm_service.generate_grounded_answer(
            sanitized_context=sanitized_context.model_dump(),
            query=query,
            retrieved_documents=retrieved_docs,
        )

        # 6. Assemble Authorized Response
        return {
            "workflow_status": "COMPLETED",
            "authoritative_results": {
                "requested_blood_group": recipient_blood_group.upper(),
                "requested_component": component.lower(),
                "eligible_candidate_count": len(eligible_candidates),
                "excluded_candidate_count": len(excluded_candidates),
                "availability_verification": sanitized_context.availability_verification,
            },
            "grounded_ai_explanation": grounded_explanation,
            "clinical_evidence_referenced": retrieved_docs[:3],
        }


clinical_coordination_service = ClinicalCoordinationService()
