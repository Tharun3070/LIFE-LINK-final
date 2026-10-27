"""Tests for LLM Emergency Intent Extraction Service and API Router."""
import pytest
from unittest.mock import patch, AsyncMock
import httpx
from app.ai.llm_service import LLMService, llm_service
from app.schemas.llm import EmergencyIntentResult


@pytest.mark.asyncio
async def test_heuristic_fallback_blood_request_extraction():
    """Confirms rule-based fallback accurately extracts blood group, units, urgency, and hospital."""
    text = "Immediate STAT requirement: Patient has severe trauma, need 3 units of O- blood at City General Hospital."
    res = await llm_service.parse_emergency_intent(text)

    assert res["emergency_type"] == "blood_request"
    assert res["blood_group"] == "O-"
    assert res["units_required"] == 3
    assert res["urgency"] == "critical"
    assert res["hospital_name"] == "City General Hospital"
    assert res["parser_used"] == "rule_based_fallback"
    assert res["confidence_score"] >= 0.8


@pytest.mark.asyncio
async def test_heuristic_fallback_organ_transfer_extraction():
    """Confirms organ transfer keyword routing and urgency detection."""
    text = "Urgent organ transfer: Donor liver ready, cold ischemic time countdown is critical."
    res = await llm_service.parse_emergency_intent(text)

    assert res["emergency_type"] == "organ_transfer"
    assert res["urgency"] == "critical"
    assert res["parser_used"] == "rule_based_fallback"


@pytest.mark.asyncio
async def test_heuristic_fallback_empty_string():
    """Empty string returns safe default without crashing."""
    res = await llm_service.parse_emergency_intent("")
    assert res["emergency_type"] == "general_emergency"
    assert "request_text" in res["missing_fields"]


@pytest.mark.asyncio
async def test_gemini_api_provider_success():
    """Verifies Gemini API structured extraction when credentials and live provider are active."""
    service = LLMService(api_key="mock_gemini_key", provider="gemini", model_name="gemini-1.5-flash")

    mock_gemini_response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"emergency_type": "blood_request", "blood_group": "AB+", "units_required": 2, "urgency": "critical", "location": "Sector 4", "hospital_name": "Apollo Trauma", "notes": "Hemorrhage", "confidence_score": 0.95, "missing_fields": []}'
                        }
                    ]
                }
            }
        ]
    }

    mock_response = httpx.Response(status_code=200, json=mock_gemini_response)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        result = await service.parse_emergency_intent("STAT 2 units of AB+ needed at Apollo Trauma")

        assert result["emergency_type"] == "blood_request"
        assert result["blood_group"] == "AB+"
        assert result["units_required"] == 2
        assert result["urgency"] == "critical"
        assert result["parser_used"] == "llm_gemini"


@pytest.mark.asyncio
async def test_llm_api_failure_graceful_fallback():
    """Verifies that an external API error (500 or timeout) falls back to deterministic heuristic."""
    service = LLMService(api_key="mock_failing_key", provider="gemini", model_name="gemini-1.5-flash", max_retries=1)

    mock_response = httpx.Response(status_code=500, content=b"Internal Server Error")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        result = await service.parse_emergency_intent("Urgent need 4 bags of A+ blood at Metro Hospital")

        # Must NOT raise exception; must fall back gracefully
        assert result["emergency_type"] == "blood_request"
        assert result["blood_group"] == "A+"
        assert result["units_required"] == 4
        assert result["parser_used"] == "rule_based_fallback"


def test_api_parse_intent_endpoint_authorized(client, doctor_token):
    """API endpoint returns structured emergency intent when authenticated."""
    response = client.post(
        "/api/v1/clinical-guidance/parse-intent",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"text": "Immediate requirement for 2 units of B+ at Memorial Hospital"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["emergency_type"] == "blood_request"
    assert data["blood_group"] == "B+"
    assert data["units_required"] == 2
    assert "parser_used" in data


def test_api_parse_intent_unauthorized(client):
    """API endpoint strictly denies unauthenticated requests."""
    response = client.post(
        "/api/v1/clinical-guidance/parse-intent",
        json={"text": "Need blood"},
    )
    assert response.status_code == 401
