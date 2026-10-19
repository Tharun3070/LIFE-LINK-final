"""Notification Provider Factory for LifeLink."""
from app.services.notification.base import NotificationProviderBase
from app.services.notification.mock_provider import MockNotificationProvider
from app.services.notification.twilio_provider import TwilioNotificationProvider
from app.core.config import settings

_mock_instance = MockNotificationProvider()
_twilio_instance = None


def get_notification_provider() -> NotificationProviderBase:
    """Returns the configured notification provider based on explicit system settings."""
    global _twilio_instance

    # Default safety rule: if MOCK_NOTIFICATIONS_ONLY is enabled or provider is "mock", always use mock
    if settings.MOCK_NOTIFICATIONS_ONLY or settings.NOTIFICATION_PROVIDER == "mock":
        return _mock_instance

    if settings.NOTIFICATION_PROVIDER == "twilio":
        if _twilio_instance is None:
            _twilio_instance = TwilioNotificationProvider()
        return _twilio_instance

    return _mock_instance
