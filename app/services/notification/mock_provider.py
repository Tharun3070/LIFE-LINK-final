"""Mock Notification Provider for Development, CI, and Project Demonstrations."""
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.services.notification.base import (
    NotificationProviderBase,
    NotificationChannel,
    NotificationDispatchResult,
    mask_phone_number,
)
from app.core.config import settings


class LiveCarrierInvocationProhibitedError(RuntimeError):
    """Raised when any simulation component attempts live SMS/Twilio/carrier invocation."""
    pass


class MockNotificationProvider(NotificationProviderBase):
    """Safe, in-memory mock notification provider guaranteeing zero external egress."""

    def __init__(self):
        self._records: List[NotificationDispatchResult] = []

    def assert_carrier_isolation(self) -> None:
        """Verifies no production credentials or carrier endpoints are contacted in mock mode."""
        if settings.MOCK_NOTIFICATIONS_ONLY and (settings.TWILIO_ACCOUNT_SID or settings.TWILIO_AUTH_TOKEN):
            if settings.TWILIO_LIVE_ENABLED:
                raise LiveCarrierInvocationProhibitedError(
                    "CRITICAL CARRIER ISOLATION FAILURE: Twilio credentials active while MOCK_NOTIFICATIONS_ONLY=True! "
                    "Mock mode strictly prohibits live carrier dispatch."
                )

    def send_sms(
        self,
        to: str,
        message: str,
        idempotency_key: Optional[str] = None,
    ) -> NotificationDispatchResult:
        self.assert_carrier_isolation()
        res = NotificationDispatchResult(
            success=True,
            status="mock_delivered",
            message_id=f"mock-sms-{uuid.uuid4().hex[:8]}",
            channel=NotificationChannel.SMS,
            recipient_masked=mask_phone_number(to),
            provider="mock",
            metadata={"idempotency_key": idempotency_key, "raw_length": len(message)},
        )
        self._records.append(res)
        return res

    def send_whatsapp(
        self,
        to: str,
        message: str,
        idempotency_key: Optional[str] = None,
    ) -> NotificationDispatchResult:
        self.assert_carrier_isolation()
        res = NotificationDispatchResult(
            success=True,
            status="mock_delivered",
            message_id=f"mock-wa-{uuid.uuid4().hex[:8]}",
            channel=NotificationChannel.WHATSAPP,
            recipient_masked=mask_phone_number(to),
            provider="mock",
            metadata={"idempotency_key": idempotency_key, "raw_length": len(message)},
        )
        self._records.append(res)
        return res

    def verify_webhook_signature(
        self,
        url: str,
        params: Dict[str, Any],
        signature: str,
    ) -> bool:
        # Mock provider accepts test signatures starting with 'mock-sig-'
        return signature.startswith("mock-sig-")

    def get_records(self) -> List[NotificationDispatchResult]:
        return list(self._records)

    def count(self) -> int:
        return len(self._records)

    def clear(self) -> None:
        self._records.clear()
