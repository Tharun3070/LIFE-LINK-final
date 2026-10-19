from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class LLMServiceInterface(ABC):
    """Abstract interface for LLM Intent Parsing and Clinical Guidance."""
    
    @abstractmethod
    async def parse_emergency_intent(self, text: str) -> Dict[str, Any]:
        """Extracts structured emergency attributes (blood group, units, urgency)."""
        raise NotImplementedError("LLM inference is scheduled for Phase 5.")


class RAGServiceInterface(ABC):
    """Abstract interface for Authorized Retrieval Augmented Generation."""
    
    @abstractmethod
    async def retrieve_authorized_context(
        self, query: str, user_role: str, hospital_id: str
    ) -> List[Dict[str, Any]]:
        """Retrieves role-filtered, HIPAA/GDPR compliant healthcare context."""
        raise NotImplementedError("RAG vector search is scheduled for Phase 5.")


class DonorRankingServiceInterface(ABC):
    """Abstract interface for XGBoost Donor Ranking."""
    
    @abstractmethod
    async def rank_donors(
        self, emergency_id: str, candidate_donor_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """Predicts response probability and ranks candidate donors."""
        raise NotImplementedError("XGBoost donor ranking model is scheduled for Phase 4.")
