"""Notification Provider Base Abstraction for LifeLink.

All providers (Mock, Twilio, and future carrier integrations) must implement
this common interface. Privacy safeguards require that phone numbers and secrets
are masked/redacted in all outputs and log statements.
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class NotificationChannel(str, Enum):
    SMS = "sms"
    WHATSAPP = "whatsapp"


class NotificationDispatchResult(BaseModel):
    success: bool
    status: str # "mock_delivered", "sent", "queued", "failed", "blocked"
    message_id: Optional[str] = None
    channel: NotificationChannel
    recipient_masked: str
    provider: str # "mock", "twilio"
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)


def mask_phone_number(phone: str) -> str:
    """Masks phone numbers to protect patient and donor privacy in logs.
    Example: '+919876543210' -> '+9198****3210'.
    """
    if not phone or len(phone) < 6:
        return "***"
    return phone[:5] + "****" + phone[-4:]


class NotificationProviderBase(ABC):
    """Abstract interface for all notification providers."""

    @abstractmethod
    def send_sms(
        self,
        to: str,
        message: str,
        idempotency_key: Optional[str] = None,
    ) -> NotificationDispatchResult:
        """Dispatches an SMS notification."""
        pass

    @abstractmethod
    def send_whatsapp(
        self,
        to: str,
        message: str,
        idempotency_key: Optional[str] = None,
    ) -> NotificationDispatchResult:
        """Dispatches a WhatsApp notification."""
        pass

    @abstractmethod
    def verify_webhook_signature(
        self,
        url: str,
        params: Dict[str, Any],
        signature: str,
    ) -> bool:
        """Verifies inbound webhook signature for carrier callbacks."""
        pass
