import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.core.config import settings


class LiveCarrierInvocationProhibitedError(RuntimeError):
    """Raised when any simulation component attempts live SMS/Twilio/carrier invocation."""
    pass


class MockNotificationRecord(BaseModel):
    id: str
    recipient: str
    channel: str  # sms, push, email, webhook
    message: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: str = "mock_delivered"


class MockNotificationProvider:
    """Test-only notification mock provider enforcing strict carrier isolation."""

    def __init__(self):
        self._records: List[MockNotificationRecord] = []

    def assert_carrier_isolation(self) -> None:
        """Verifies no production credentials or carrier endpoints are configured for live dispatch in simulation."""
        if not settings.MOCK_NOTIFICATIONS_ONLY and (settings.TWILIO_ACCOUNT_SID or settings.TWILIO_AUTH_TOKEN):
            raise LiveCarrierInvocationProhibitedError(
                "CRITICAL CARRIER ISOLATION FAILURE: Twilio credentials detected in environment with live notifications enabled! "
                "Simulation must execute with mock notification providers only."
            )

    def dispatch(
        self,
        recipient: str,
        message: str,
        channel: str = "sms",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MockNotificationRecord:
        """Records a simulated notification dispatch."""
        self.assert_carrier_isolation()

        import uuid
        record = MockNotificationRecord(
            id=f"mock-notif-{uuid.uuid4().hex[:8]}",
            recipient=recipient,
            channel=channel,
            message=message,
            metadata=metadata or {},
            status="mock_delivered",
        )
        self._records.append(record)
        return record

    def get_records(self) -> List[MockNotificationRecord]:
        return list(self._records)

    def count(self) -> int:
        return len(self._records)

    def clear(self) -> None:
        self._records.clear()


# Global singleton mock notification provider
mock_notification_provider = MockNotificationProvider()
