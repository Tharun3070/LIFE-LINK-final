"""Tests for Priority 3: Twilio SMS and WhatsApp Notification Provider Integration & Safety Controls."""
import base64
import hashlib
import hmac
import pytest
from unittest.mock import patch, MagicMock
from app.services.notification.base import (
    NotificationChannel,
    NotificationDispatchResult,
    mask_phone_number,
)
from app.services.notification.mock_provider import MockNotificationProvider
from app.services.notification.twilio_provider import TwilioNotificationProvider
from app.services.notification.factory import get_notification_provider
from app.core.config import settings


def test_default_notification_provider_is_mock(client):
    """By default, the platform selects the safe mock notification provider."""
    provider = get_notification_provider()
    assert isinstance(provider, MockNotificationProvider)

    resp = client.get("/api/v1/notifications/provider-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "mock"
    assert data["mockNotificationsOnly"] is True
    assert data["liveEnabled"] is False


def test_phone_number_masking_privacy():
    """Phone numbers are masked to protect donor and patient privacy in logs and audits."""
    assert mask_phone_number("+919876543210") == "+9198****3210"
    assert mask_phone_number("+14155552671") == "+1415****2671"
    assert mask_phone_number("123") == "***"


def test_mock_provider_sms_and_whatsapp_dispatch():
    """Mock provider dispatches SMS and WhatsApp in memory without external egress."""
    provider = MockNotificationProvider()
    provider.clear()

    res_sms = provider.send_sms(to="+919876543210", message="Test emergency SMS")
    assert res_sms.success is True
    assert res_sms.status == "mock_delivered"
    assert res_sms.channel == NotificationChannel.SMS
    assert res_sms.recipient_masked == "+9198****3210"

    res_wa = provider.send_whatsapp(to="+919876543210", message="Test emergency WhatsApp")
    assert res_wa.success is True
    assert res_wa.status == "mock_delivered"
    assert res_wa.channel == NotificationChannel.WHATSAPP

    assert provider.count() == 2


def test_twilio_safety_gate_blocks_when_live_disabled():
    """Twilio provider refuses to send external messages when TWILIO_LIVE_ENABLED=False."""
    provider = TwilioNotificationProvider(
        account_sid="AC_test_sid_0000000000000000000000",
        auth_token="test_auth_token_secret_12345",
        from_phone="+15005550006",
        live_enabled=False,  # Explicitly disabled
    )

    res = provider.send_sms(to="+919876543210", message="Emergency alert")
    assert res.success is False
    assert res.status == "blocked"
    assert "blocked" in res.error.lower()


def test_twilio_missing_credentials_fails_safely():
    """Twilio provider fails safely with descriptive message when credentials are missing."""
    provider = TwilioNotificationProvider(
        account_sid="",
        auth_token="",
        live_enabled=True,
    )
    res = provider.send_sms(to="+919876543210", message="Emergency alert")
    assert res.success is False
    assert res.status == "blocked" or res.status == "failed"
    assert "missing" in res.error.lower() or "blocked" in res.error.lower()


def test_twilio_idempotency_prevents_duplicate_sends():
    """Duplicate requests with the same idempotency key replay cached response without re-sending."""
    provider = TwilioNotificationProvider(
        account_sid="AC_test_sid_0000000000000000000000",
        auth_token="test_auth_token_secret_12345",
        from_phone="+15005550006",
        live_enabled=True,
    )

    # Mock settings so MOCK_NOTIFICATIONS_ONLY doesn't block the mock unit test
    with patch("app.services.notification.twilio_provider.settings.MOCK_NOTIFICATIONS_ONLY", False):
        with patch("httpx.Client.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.json.return_value = {"sid": "SM_IDEMPOTENT_001", "status": "queued"}
            mock_post.return_value = mock_resp

            # First send
            res1 = provider.send_sms(
                to="+919876543210",
                message="Urgent blood needed",
                idempotency_key="idemp-key-emergency-001",
            )
            assert res1.success is True
            assert res1.message_id == "SM_IDEMPOTENT_001"
            assert mock_post.call_count == 1

            # Second send with same idempotency key
            res2 = provider.send_sms(
                to="+919876543210",
                message="Urgent blood needed",
                idempotency_key="idemp-key-emergency-001",
            )
            assert res2.success is True
            assert res2.message_id == "SM_IDEMPOTENT_001"
            # Crucial: call_count remains 1 (no duplicate outbound HTTP request!)
            assert mock_post.call_count == 1


def test_twilio_recipient_rate_limiting():
    """Sending more than the allowed rate limit per recipient per hour is blocked."""
    provider = TwilioNotificationProvider(
        account_sid="AC_test_sid_0000000000000000000000",
        auth_token="test_auth_token_secret_12345",
        from_phone="+15005550006",
        live_enabled=True,
    )

    with patch("app.services.notification.twilio_provider.settings.MOCK_NOTIFICATIONS_ONLY", False):
        with patch("httpx.Client.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.json.return_value = {"sid": "SM_RATE_001", "status": "queued"}
            mock_post.return_value = mock_resp

            recipient = "+919876543999"
            # Send 5 allowed requests
            for i in range(5):
                res = provider.send_sms(to=recipient, message=f"Alert #{i}")
                assert res.success is True

            # 6th request within the hour must be blocked by rate limiter
            res_blocked = provider.send_sms(to=recipient, message="Alert #6")
            assert res_blocked.success is False
            assert res_blocked.status == "blocked"
            assert "rate limit exceeded" in res_blocked.error.lower()


def test_twilio_circuit_breaker_on_repeated_errors():
    """5 consecutive carrier failures trip the circuit breaker and suspend dispatches."""
    provider = TwilioNotificationProvider(
        account_sid="AC_test_sid_0000000000000000000000",
        auth_token="test_auth_token_secret_12345",
        from_phone="+15005550006",
        live_enabled=True,
        max_retries=1,
    )

    with patch("app.services.notification.twilio_provider.settings.MOCK_NOTIFICATIONS_ONLY", False):
        with patch("httpx.Client.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 503
            mock_resp.text = "Service Unavailable"
            mock_post.return_value = mock_resp

            # Cause 5 failures to trip the circuit
            for i in range(5):
                res = provider.send_sms(to=f"+91987654300{i}", message="Alert")
                assert res.success is False

            # 6th call should be immediately blocked by circuit breaker without HTTP call
            call_count_before = mock_post.call_count
            res_tripped = provider.send_sms(to="+919876543099", message="Alert")
            assert res_tripped.success is False
            assert res_tripped.status == "blocked"
            assert "circuit breaker open" in res_tripped.error.lower()
            assert mock_post.call_count == call_count_before


def test_twilio_webhook_signature_verification():
    """Verifies that the HMAC-SHA1 signature verification algorithm accurately validates signatures."""
    auth_token = "my_twilio_secret_token_abc123"
    provider = TwilioNotificationProvider(auth_token=auth_token)

    url = "https://lifelink.org/api/v1/notifications/twilio/status-callback"
    params = {
        "MessageSid": "SM1234567890abcdef",
        "MessageStatus": "delivered",
        "To": "+919876543210",
    }

    # Construct genuine Twilio signature
    sorted_params = sorted(params.items(), key=lambda x: x[0])
    data_to_sign = url + "".join(f"{k}{v}" for k, v in sorted_params)
    computed = hmac.new(auth_token.encode("utf-8"), data_to_sign.encode("utf-8"), hashlib.sha1).digest()
    valid_signature = base64.b64encode(computed).decode("utf-8")

    # Genuine signature passes
    assert provider.verify_webhook_signature(url, params, valid_signature) is True

    # Tampered signature fails
    assert provider.verify_webhook_signature(url, params, "tampered_fake_signature_xyz==") is False

    # Tampered params fail
    tampered_params = dict(params)
    tampered_params["MessageStatus"] = "failed"
    assert provider.verify_webhook_signature(url, tampered_params, valid_signature) is False


def test_twilio_webhook_callback_endpoint(client):
    """Twilio status callback endpoint receives delivery events."""
    resp = client.post(
        "/api/v1/notifications/twilio/status-callback",
        data={
            "MessageSid": "SM999988887777",
            "MessageStatus": "delivered",
            "To": "+919876543210",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "recorded"
    assert data["messageId"] == "SM999988887777"
    assert data["deliveryStatus"] == "delivered"
