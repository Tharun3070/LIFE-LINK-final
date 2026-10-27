"""Production-ready Twilio Notification Provider for LifeLink SMS and WhatsApp.

MANDATORY SAFETY AND CARRIER ISOLATION CONTROLS:
1. Live activation strictly requires `TWILIO_LIVE_ENABLED=True` and `MOCK_NOTIFICATIONS_ONLY=False`.
2. Idempotency guarantees prevent duplicate donor dispatches.
3. Rate-limiting protects recipient privacy and prevents carrier spam.
4. Circuit breaker suspends calls during provider outages.
5. All logs mask recipient phone numbers and sanitize authentication tokens.
"""
import hmac
import hashlib
import base64
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
import httpx
from app.services.notification.base import (
    NotificationProviderBase,
    NotificationChannel,
    NotificationDispatchResult,
    mask_phone_number,
)
from app.core.config import settings
from app.core.logging import logger


class TwilioNotificationProvider(NotificationProviderBase):
    """Production Twilio adapter for SMS and WhatsApp with cost and safety controls."""

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_phone: Optional[str] = None,
        whatsapp_from: Optional[str] = None,
        live_enabled: Optional[bool] = None,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
    ):
        self.account_sid = account_sid or settings.TWILIO_ACCOUNT_SID
        self.auth_token = auth_token or settings.TWILIO_AUTH_TOKEN
        self.from_phone = from_phone or settings.TWILIO_PHONE_NUMBER
        self.whatsapp_from = whatsapp_from or settings.TWILIO_WHATSAPP_FROM
        self.live_enabled = live_enabled if live_enabled is not None else settings.TWILIO_LIVE_ENABLED
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

        # In-memory controls
        self._idempotency_cache: Dict[str, NotificationDispatchResult] = {}
        self._recipient_history: Dict[str, List[datetime]] = {}
        self._consecutive_failures = 0
        self._circuit_broken_until: Optional[datetime] = None

    def _check_safety_gate(self) -> Optional[NotificationDispatchResult]:
        """Enforces live activation gates before any outbound HTTP attempt."""
        if settings.MOCK_NOTIFICATIONS_ONLY:
            return NotificationDispatchResult(
                success=False,
                status="blocked",
                channel=NotificationChannel.SMS,
                recipient_masked="***",
                provider="twilio",
                error="Live delivery blocked: MOCK_NOTIFICATIONS_ONLY is enabled.",
            )

        if not self.live_enabled:
            return NotificationDispatchResult(
                success=False,
                status="blocked",
                channel=NotificationChannel.SMS,
                recipient_masked="***",
                provider="twilio",
                error="Live delivery blocked: TWILIO_LIVE_ENABLED is False. Requires explicit human activation.",
            )

        if not self.account_sid or not self.auth_token:
            return NotificationDispatchResult(
                success=False,
                status="failed",
                channel=NotificationChannel.SMS,
                recipient_masked="***",
                provider="twilio",
                error="Twilio credentials (ACCOUNT_SID or AUTH_TOKEN) are missing.",
            )

        # Circuit breaker check
        if self._circuit_broken_until:
            if datetime.now(timezone.utc) < self._circuit_broken_until:
                return NotificationDispatchResult(
                    success=False,
                    status="blocked",
                    channel=NotificationChannel.SMS,
                    recipient_masked="***",
                    provider="twilio",
                    error="Circuit breaker OPEN: Outbound Twilio dispatches suspended due to repeated provider failures.",
                )
            else:
                # Reset circuit after backoff window
                self._circuit_broken_until = None
                self._consecutive_failures = 0

        return None

    def _check_rate_limit(self, recipient: str) -> bool:
        """Enforces maximum allowed alerts per recipient per hour."""
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        history = self._recipient_history.setdefault(recipient, [])
        # Prune old records
        self._recipient_history[recipient] = [t for t in history if t > one_hour_ago]

        limit = settings.NOTIFICATION_RATE_LIMIT_PER_RECIPIENT_PER_HOUR
        if len(self._recipient_history[recipient]) >= limit:
            return False

        self._recipient_history[recipient].append(now)
        return True

    def _execute_twilio_request(
        self,
        from_num: str,
        to_num: str,
        body: str,
        channel: NotificationChannel,
        idempotency_key: Optional[str] = None,
    ) -> NotificationDispatchResult:
        masked_to = mask_phone_number(to_num)

        # Check idempotency
        if idempotency_key and idempotency_key in self._idempotency_cache:
            cached = self._idempotency_cache[idempotency_key]
            logger.info(f"Twilio {channel.value} dispatch deduplicated via idempotency key for {masked_to}")
            return cached

        # Check rate limit
        if not self._check_rate_limit(to_num):
            return NotificationDispatchResult(
                success=False,
                status="blocked",
                channel=channel,
                recipient_masked=masked_to,
                provider="twilio",
                error=f"Recipient rate limit exceeded ({settings.NOTIFICATION_RATE_LIMIT_PER_RECIPIENT_PER_HOUR}/hr).",
            )

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        data = {
            "From": from_num,
            "To": to_num,
            "Body": body,
        }

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    resp = client.post(
                        url,
                        data=data,
                        auth=(self.account_sid, self.auth_token),
                    )

                if resp.status_code in [200, 201]:
                    self._consecutive_failures = 0
                    resp_data = resp.json()
                    msg_id = resp_data.get("sid", f"SM{attempt}")
                    result = NotificationDispatchResult(
                        success=True,
                        status="sent",
                        message_id=msg_id,
                        channel=channel,
                        recipient_masked=masked_to,
                        provider="twilio",
                        metadata={"twilio_status": resp_data.get("status", "queued")},
                    )
                    if idempotency_key:
                        self._idempotency_cache[idempotency_key] = result
                    logger.info(f"Twilio {channel.value} dispatched successfully to {masked_to} (SID: {msg_id})")
                    return result

                elif 400 <= resp.status_code < 500:
                    # Client errors (e.g. invalid phone number) should not be retried blindly
                    err_msg = f"Twilio HTTP {resp.status_code}: {resp.text}"
                    logger.error(f"Twilio client error delivering to {masked_to}: {err_msg}")
                    return NotificationDispatchResult(
                        success=False,
                        status="failed",
                        channel=channel,
                        recipient_masked=masked_to,
                        provider="twilio",
                        error=err_msg,
                    )
                else:
                    # 5xx Server Error - eligible for bounded retry
                    err_msg = f"Twilio 5xx server error (status {resp.status_code})"
                    last_error = err_msg

            except Exception as ex:
                last_error = str(ex)
                logger.warning(f"Twilio dispatch attempt {attempt} failed: {ex}")

            if attempt < self.max_retries:
                time.sleep(0.5 * (2 ** (attempt - 1)))

        # If all retries failed, increment circuit breaker failures
        self._consecutive_failures += 1
        if self._consecutive_failures >= 5:
            self._circuit_broken_until = datetime.now(timezone.utc) + timedelta(minutes=15)
            logger.critical("Twilio circuit breaker tripped: 5 consecutive failures recorded.")

        return NotificationDispatchResult(
            success=False,
            status="failed",
            channel=channel,
            recipient_masked=masked_to,
            provider="twilio",
            error=f"Twilio dispatch failed after {self.max_retries} attempts: {last_error}",
        )

    def send_sms(
        self,
        to: str,
        message: str,
        idempotency_key: Optional[str] = None,
    ) -> NotificationDispatchResult:
        gate_result = self._check_safety_gate()
        if gate_result:
            gate_result.channel = NotificationChannel.SMS
            gate_result.recipient_masked = mask_phone_number(to)
            return gate_result
                        # Demo safety: allow live SMS only to the configured demo recipient.
        allowed_recipient = (settings.TWILIO_DEMO_RECIPIENT or "").strip()

        if not allowed_recipient:
            return NotificationDispatchResult(
                success=False,
                status="blocked",
                channel=NotificationChannel.SMS,
                recipient_masked=mask_phone_number(to),
                provider="twilio",
                error="Live SMS blocked: demo recipient is not configured.",
            )
        
        if to.strip() != allowed_recipient:
            return NotificationDispatchResult(
                success=False,
                status="blocked",
                channel=NotificationChannel.SMS,
                recipient_masked=mask_phone_number(to),
                provider="twilio",
                error="Live SMS blocked: recipient is not allowlisted for the demo.",
            )
        
        from_num = self.from_phone
        if not from_num:
            return NotificationDispatchResult(
                success=False,
                status="failed",
                channel=NotificationChannel.SMS,
                recipient_masked=mask_phone_number(to),
                provider="twilio",
                error="Twilio sender phone number is not configured.",
            )

        return self._execute_twilio_request(
            from_num=from_num,
            to_num=to,
            body=message,
            channel=NotificationChannel.SMS,
            idempotency_key=idempotency_key,
        )

    def send_whatsapp(
        self,
        to: str,
        message: str,
        idempotency_key: Optional[str] = None,
    ) -> NotificationDispatchResult:
        gate_result = self._check_safety_gate()
        if gate_result:
            gate_result.channel = NotificationChannel.WHATSAPP
            gate_result.recipient_masked = mask_phone_number(to)
            return gate_result

        from_num = self.whatsapp_from if self.whatsapp_from.startswith("whatsapp:") else f"whatsapp:{self.whatsapp_from}"
        to_num = to if to.startswith("whatsapp:") else f"whatsapp:{to}"

        return self._execute_twilio_request(
            from_num=from_num,
            to_num=to_num,
            body=message,
            channel=NotificationChannel.WHATSAPP,
            idempotency_key=idempotency_key,
        )

    def verify_webhook_signature(
        self,
        url: str,
        params: Dict[str, Any],
        signature: str,
    ) -> bool:
        """Verifies Twilio's X-Twilio-Signature header using HMAC-SHA1."""
        if not self.auth_token or not signature:
            return False

        # 1. Sort POST parameters alphabetically by key
        # 2. Append key and value to the request URL
        sorted_params = sorted(params.items(), key=lambda x: x[0])
        data_to_sign = url + "".join(f"{k}{v}" for k, v in sorted_params)

        computed = hmac.new(
            self.auth_token.encode("utf-8"),
            data_to_sign.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        expected_sig = base64.b64encode(computed).decode("utf-8")

        return hmac.compare_digest(expected_sig, signature)
