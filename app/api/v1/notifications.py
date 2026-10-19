"""Notification Management and Carrier Webhook Endpoints."""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Header, HTTPException, status
from app.services.notification.factory import get_notification_provider
from app.core.config import settings
from app.core.logging import logger

router = APIRouter(prefix="/notifications", tags=["Notifications & Telephony"])


@router.get(
    "/provider-status",
    summary="Get Notification Provider Status",
    description="Returns current active notification provider and safety gate configuration.",
)
def get_provider_status():
    provider = get_notification_provider()
    return {
        "provider": getattr(provider, "provider_name", "mock" if settings.MOCK_NOTIFICATIONS_ONLY else settings.NOTIFICATION_PROVIDER),
        "mockNotificationsOnly": settings.MOCK_NOTIFICATIONS_ONLY,
        "liveEnabled": settings.TWILIO_LIVE_ENABLED,
        "rateLimitPerHour": settings.NOTIFICATION_RATE_LIMIT_PER_RECIPIENT_PER_HOUR,
        "spendCeilingUsd": settings.NOTIFICATION_SPEND_CEILING_USD,
        "configuredChannels": ["sms", "whatsapp"],
    }


@router.post(
    "/twilio/status-callback",
    summary="Twilio Delivery Status Webhook Callback",
    description="Receives delivery receipt callbacks from Twilio with signature validation.",
)
async def twilio_status_callback(
    request: Request,
    x_twilio_signature: Optional[str] = Header(None, alias="X-Twilio-Signature"),
):
    # Parse form or JSON parameters
    form_data = await request.form()
    params = dict(form_data)
    if not params:
        try:
            params = await request.json()
        except Exception:
            params = {}

    provider = get_notification_provider()
    full_url = str(request.url)

    # In production with live Twilio, verify signature
    if settings.TWILIO_LIVE_ENABLED and not settings.MOCK_NOTIFICATIONS_ONLY:
        if not x_twilio_signature or not provider.verify_webhook_signature(full_url, params, x_twilio_signature):
            logger.warning("Rejected Twilio status callback: Invalid X-Twilio-Signature")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid Twilio webhook signature",
            )

    message_sid = params.get("MessageSid") or params.get("SmsSid") or "unknown"
    message_status = params.get("MessageStatus") or params.get("SmsStatus") or "received"
    error_code = params.get("ErrorCode")

    logger.info(f"Twilio status callback received: SID={message_sid}, status={message_status}, error={error_code}")

    return {
        "status": "recorded",
        "messageId": message_sid,
        "deliveryStatus": message_status,
        "errorCode": error_code,
    }
