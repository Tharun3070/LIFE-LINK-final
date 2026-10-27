"""Tests for Twilio SMS and WhatsApp Notification Provider Integration & Safety Controls."""

import base64
import hashlib
import hmac
from unittest.mock import MagicMock, patch

from app.services.notification.base import (
    NotificationChannel,
    mask_phone_number,
)
from app.services.notification.factory import get_notification_provider
from app.services.notification.mock_provider import MockNotificationProvider
from app.services.notification.twilio_provider import TwilioNotificationProvider


def test_default_notification_provider_is_mock(client):
    """The platform selects the safe mock notification provider by default."""
    provider = get_notification_provider()

    assert isinstance(provider, MockNotificationProvider)

    response = client.get("/api/v1/notifications/provider-status")

    assert response.status_code == 200

    data = response.json()

    assert data["provider"] == "mock"
    assert data["mockNotificationsOnly"] is True
    assert data["liveEnabled"] is False


def test_phone_number_masking_privacy():
    """Phone numbers are masked to protect donor and patient privacy."""
    assert mask_phone_number("+919876543210") == "+9198****3210"
    assert mask_phone_number("+14155552671") == "+1415****2671"
    assert mask_phone_number("123") == "***"


def test_mock_provider_sms_and_whatsapp_dispatch():
    """Mock SMS and WhatsApp dispatches do not use external services."""
    provider = MockNotificationProvider()
    provider.clear()

    sms_result = provider.send_sms(
        to="+919876543210",
        message="Test emergency SMS",
    )

    assert sms_result.success is True
    assert sms_result.status == "mock_delivered"
    assert sms_result.channel == NotificationChannel.SMS
    assert sms_result.recipient_masked == "+9198****3210"

    whatsapp_result = provider.send_whatsapp(
        to="+919876543210",
        message="Test emergency WhatsApp",
    )

    assert whatsapp_result.success is True
    assert whatsapp_result.status == "mock_delivered"
    assert whatsapp_result.channel == NotificationChannel.WHATSAPP

    assert provider.count() == 2


def test_twilio_safety_gate_blocks_when_live_disabled():
    """Twilio refuses external messages when live sending is disabled."""
    provider = TwilioNotificationProvider(
        account_sid="AC_test_sid_0000000000000000000000",
        auth_token="test_auth_token_secret_12345",
        from_phone="+15005550006",
        live_enabled=False,
    )

    with patch("httpx.Client.post") as mock_post:
        result = provider.send_sms(
            to="+919876543210",
            message="Emergency alert",
        )

    assert result.success is False
    assert result.status == "blocked"
    assert "blocked" in result.error.lower()
    mock_post.assert_not_called()


def test_twilio_missing_credentials_fails_safely():
    """Missing Twilio credentials must not allow an external message."""
    provider = TwilioNotificationProvider(
        account_sid="",
        auth_token="",
        live_enabled=True,
    )

    with patch(
        "app.services.notification.twilio_provider.settings.MOCK_NOTIFICATIONS_ONLY",
        False,
    ):
        with patch("httpx.Client.post") as mock_post:
            result = provider.send_sms(
                to="+919876543210",
                message="Emergency alert",
            )

    assert result.success is False
    assert result.status in {"blocked", "failed"}
    assert (
        "missing" in result.error.lower()
        or "blocked" in result.error.lower()
    )
    mock_post.assert_not_called()


def test_twilio_blocks_sms_when_demo_recipient_is_not_configured():
    """Live SMS must be blocked when no demo recipient is configured."""
    provider = TwilioNotificationProvider(
        account_sid="AC_test_sid_0000000000000000000000",
        auth_token="test_auth_token_secret_12345",
        from_phone="+15005550006",
        live_enabled=True,
    )

    with (
        patch(
            "app.services.notification.twilio_provider.settings.MOCK_NOTIFICATIONS_ONLY",
            False,
        ),
        patch(
            "app.services.notification.twilio_provider.settings.TWILIO_DEMO_RECIPIENT",
            "",
        ),
        patch("httpx.Client.post") as mock_post,
    ):
        result = provider.send_sms(
            to="+919876543210",
            message="Test emergency SMS",
        )

    assert result.success is False
    assert result.status == "blocked"
    assert "demo recipient" in result.error.lower()
    mock_post.assert_not_called()


def test_twilio_blocks_sms_to_non_allowlisted_recipient():
    """Live SMS must not be sent to any number other than the demo recipient."""
    provider = TwilioNotificationProvider(
        account_sid="AC_test_sid_0000000000000000000000",
        auth_token="test_auth_token_secret_12345",
        from_phone="+15005550006",
        live_enabled=True,
    )

    with (
        patch(
            "app.services.notification.twilio_provider.settings.MOCK_NOTIFICATIONS_ONLY",
            False,
        ),
        patch(
            "app.services.notification.twilio_provider.settings.TWILIO_DEMO_RECIPIENT",
            "+919876543210",
        ),
        patch("httpx.Client.post") as mock_post,
    ):
        result = provider.send_sms(
            to="+919876543999",
            message="This should be blocked",
        )

    assert result.success is False
    assert result.status == "blocked"
    assert "allowlisted" in result.error.lower()
    mock_post.assert_not_called()


def test_twilio_idempotency_prevents_duplicate_sends():
    """Repeated requests with one idempotency key send only once."""
    provider = TwilioNotificationProvider(
        account_sid="AC_test_sid_0000000000000000000000",
        auth_token="test_auth_token_secret_12345",
        from_phone="+15005550006",
        live_enabled=True,
    )

    recipient = "+919876543210"

    with (
        patch(
            "app.services.notification.twilio_provider.settings.MOCK_NOTIFICATIONS_ONLY",
            False,
        ),
        patch(
            "app.services.notification.twilio_provider.settings.TWILIO_DEMO_RECIPIENT",
            recipient,
        ),
        patch("httpx.Client.post") as mock_post,
    ):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "sid": "SM_IDEMPOTENT_001",
            "status": "queued",
        }
        mock_post.return_value = mock_response

        first_result = provider.send_sms(
            to=recipient,
            message="Demo notification",
            idempotency_key="idemp-key-emergency-001",
        )

        assert first_result.success is True
        assert first_result.message_id == "SM_IDEMPOTENT_001"
        assert mock_post.call_count == 1

        second_result = provider.send_sms(
            to=recipient,
            message="Demo notification",
            idempotency_key="idemp-key-emergency-001",
        )

        assert second_result.success is True
        assert second_result.message_id == "SM_IDEMPOTENT_001"

        # The repeated request must not trigger another HTTP request.
        assert mock_post.call_count == 1


def test_twilio_recipient_rate_limiting():
    """Requests exceeding the recipient rate limit are blocked."""
    provider = TwilioNotificationProvider(
        account_sid="AC_test_sid_0000000000000000000000",
        auth_token="test_auth_token_secret_12345",
        from_phone="+15005550006",
        live_enabled=True,
    )

    recipient = "+919876543999"

    with (
        patch(
            "app.services.notification.twilio_provider.settings.MOCK_NOTIFICATIONS_ONLY",
            False,
        ),
        patch(
            "app.services.notification.twilio_provider.settings.TWILIO_DEMO_RECIPIENT",
            recipient,
        ),
        patch("httpx.Client.post") as mock_post,
    ):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "sid": "SM_RATE_001",
            "status": "queued",
        }
        mock_post.return_value = mock_response

        # Five requests should pass under the configured limit.
        for index in range(5):
            result = provider.send_sms(
                to=recipient,
                message=f"Demo alert #{index}",
            )
            assert result.success is True

        # The sixth request should be blocked by the rate limiter.
        blocked_result = provider.send_sms(
            to=recipient,
            message="Demo alert #6",
        )

        assert blocked_result.success is False
        assert blocked_result.status == "blocked"
        assert "rate limit exceeded" in blocked_result.error.lower()
        assert mock_post.call_count == 5


def test_twilio_circuit_breaker_on_repeated_errors():
    """Repeated carrier failures trip the circuit breaker."""
    provider = TwilioNotificationProvider(
        account_sid="AC_test_sid_0000000000000000000000",
        auth_token="test_auth_token_secret_12345",
        from_phone="+15005550006",
        live_enabled=True,
        max_retries=1,
    )

    recipients = [
        "+919876543000",
        "+919876543001",
        "+919876543002",
        "+919876543003",
        "+919876543004",
    ]

    with (
        patch(
            "app.services.notification.twilio_provider.settings.MOCK_NOTIFICATIONS_ONLY",
            False,
        ),
        patch("httpx.Client.post") as mock_post,
    ):
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"
        mock_post.return_value = mock_response

        # Each simulated destination is explicitly allowlisted for its
        # individual test call. No real HTTP request is made.
        for recipient in recipients:
            with patch(
                "app.services.notification.twilio_provider.settings.TWILIO_DEMO_RECIPIENT",
                recipient,
            ):
                result = provider.send_sms(
                    to=recipient,
                    message="Simulated test alert",
                )

            assert result.success is False

        # The circuit breaker should now be open.
        call_count_before = mock_post.call_count

        with patch(
            "app.services.notification.twilio_provider.settings.TWILIO_DEMO_RECIPIENT",
            "+919876543099",
        ):
            blocked_result = provider.send_sms(
                to="+919876543099",
                message="Simulated test alert",
            )

        assert blocked_result.success is False
        assert blocked_result.status == "blocked"
        assert "circuit breaker open" in blocked_result.error.lower()

        # No additional HTTP request should occur after the circuit trips.
        assert mock_post.call_count == call_count_before


def test_twilio_webhook_signature_verification():
    """Valid Twilio signatures pass; tampered signatures fail."""
    auth_token = "my_twilio_secret_token_abc123"
    provider = TwilioNotificationProvider(auth_token=auth_token)

    url = "https://lifelink.org/api/v1/notifications/twilio/status-callback"

    params = {
        "MessageSid": "SM1234567890abcdef",
        "MessageStatus": "delivered",
        "To": "+919876543210",
    }

    sorted_params = sorted(params.items(), key=lambda item: item[0])
    data_to_sign = url + "".join(
        f"{key}{value}" for key, value in sorted_params
    )

    computed_signature = hmac.new(
        auth_token.encode("utf-8"),
        data_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()

    valid_signature = base64.b64encode(
        computed_signature
    ).decode("utf-8")

    assert provider.verify_webhook_signature(
        url,
        params,
        valid_signature,
    ) is True

    assert provider.verify_webhook_signature(
        url,
        params,
        "tampered_fake_signature_xyz==",
    ) is False

    tampered_params = dict(params)
    tampered_params["MessageStatus"] = "failed"

    assert provider.verify_webhook_signature(
        url,
        tampered_params,
        valid_signature,
    ) is False


def test_twilio_webhook_callback_endpoint(client):
    """The webhook endpoint records a delivery status callback."""
    response = client.post(
        "/api/v1/notifications/twilio/status-callback",
        data={
            "MessageSid": "SM999988887777",
            "MessageStatus": "delivered",
            "To": "+919876543210",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "recorded"
    assert data["messageId"] == "SM999988887777"
    assert data["deliveryStatus"] == "delivered"