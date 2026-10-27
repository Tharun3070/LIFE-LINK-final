"""Pydantic schemas for LLM Intent Parsing and Structured Emergency Attributes."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class EmergencyIntentRequest(BaseModel):
    text: str = Field(..., min_length=3, description="Unstructured clinical request or emergency dispatch text")


class EmergencyIntentResult(BaseModel):
    emergency_type: str = Field(..., description="Categorized emergency type (blood_request, organ_transfer, ambulance_dispatch, general_emergency)")
    blood_group: Optional[str] = Field(None, description="Extracted standard ABO/Rh blood group if applicable")
    units_required: Optional[int] = Field(None, description="Number of blood or component units requested")
    urgency: str = Field("high", description="Urgency level (critical, high, medium, low)")
    location: Optional[str] = Field(None, description="Extracted emergency location or address")
    hospital_name: Optional[str] = Field(None, description="Referenced hospital name or facility")
    notes: Optional[str] = Field(None, description="Clinical summary notes")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence score")
    missing_fields: List[str] = Field(default_factory=list, description="Critical information missing for complete dispatch")
    parser_used: str = Field(..., description="Provider or fallback engine used for extraction")


class GroundedExplanationRequest(BaseModel):
    query: Optional[str] = Field(None, description="Clinical query or question about the match")
    sanitized_context: Dict[str, Any] = Field(..., description="Privacy-sanitized matching context")
    include_clinical_guidelines: bool = Field(True, description="Whether to fetch and cite relevant clinical guidelines")


class GroundedExplanationResponse(BaseModel):
    explanation: str = Field(..., description="Grounded clinical explanation text")
    provider_used: str = Field(..., description="Provider used: gemini, openai, or deterministic_grounded_fallback")
    is_grounded: bool = Field(True, description="Whether output was verified against supplied context")
    citations: List[Dict[str, str]] = Field(default_factory=list, description="Citations from clinical guidelines")
    safety_flags: List[str] = Field(default_factory=list, description="Safety or sanitization flags applied")
    clinical_disclaimer: str = Field(..., description="Transfusion crossmatch safety notice")

