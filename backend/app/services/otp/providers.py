"""
NAADAMAYA OTP delivery providers.

The OTP service never talks to an SMS company directly. It talks to the
OtpProvider interface, so switching provider (MSG91, Twilio, Exotel, AWS SNS,
Firebase, ...) means adding one class and changing OTP_PROVIDER in .env.

    provider = get_otp_provider()
    provider.send(phone_e164, code)

Providers:
  mock    development only. Delivers nothing; the code is the fixed
          OTP_DEV_FIXED_CODE. config.py refuses OTP_PROVIDER=mock in production.
  msg91   MSG91 Send OTP (Indian SMS, DLT-template based).
  twilio  Twilio Programmable Messaging.

The provider only DELIVERS a code the service already generated and hashed.
Verification is done by the service against the stored hash, never by the
provider. The code is never logged: not here, not anywhere.
"""

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger
from app.utils.phone import mask_phone

log = get_logger("naadamaya.otp.provider")

HTTP_TIMEOUT_SECONDS = 10


class OtpProvider(ABC):
    name: str = "base"

    @abstractmethod
    def send(self, phone_e164: str, code: str) -> None:
        """Delivers `code` to the phone. Raises ServiceUnavailableError on failure."""


def _post(url: str, data: bytes, headers: dict[str, str]) -> None:
    """Small HTTPS POST helper. Raises ServiceUnavailableError, logging no secrets."""
    if not url.lower().startswith("https://"):
        raise ServiceUnavailableError("We could not send the code. Please try again.")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310
            if response.status >= 300:
                raise ServiceUnavailableError("We could not send the code. Please try again.")
    except urllib.error.HTTPError as exc:
        log.error("sms provider rejected the request (status %s)", exc.code)
        raise ServiceUnavailableError("We could not send the code. Please try again.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log.error("sms provider could not be reached")
        raise ServiceUnavailableError("We could not send the code. Please try again.") from exc


# ==========================================================
# Mock (development)
# ==========================================================
class MockOtpProvider(OtpProvider):
    name = "mock"

    def send(self, phone_e164: str, code: str) -> None:
        # Nothing is sent. The code is deliberately NOT logged.
        log.info("mock otp: no SMS sent to %s (development)", mask_phone(phone_e164))


# ==========================================================
# MSG91
# ==========================================================
class Msg91OtpProvider(OtpProvider):
    name = "msg91"
    URL = "https://control.msg91.com/api/v5/otp"

    def __init__(self) -> None:
        if not settings.msg91_auth_key or not settings.msg91_template_id:
            raise ServiceUnavailableError("SMS delivery is not configured.")

    def send(self, phone_e164: str, code: str) -> None:
        mobile = phone_e164.lstrip("+")  # MSG91 wants digits with country code
        query = urllib.parse.urlencode(
            {
                "template_id": settings.msg91_template_id,
                "mobile": mobile,
                "otp": code,
                "otp_expiry": max(1, settings.otp_expire_seconds // 60),
            }
        )
        _post(
            f"{self.URL}?{query}",
            data=json.dumps({}).encode(),
            headers={"authkey": settings.msg91_auth_key, "Content-Type": "application/json"},
        )


# ==========================================================
# Twilio
# ==========================================================
class TwilioOtpProvider(OtpProvider):
    name = "twilio"

    def __init__(self) -> None:
        if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number):
            raise ServiceUnavailableError("SMS delivery is not configured.")

    def send(self, phone_e164: str, code: str) -> None:
        minutes = max(1, settings.otp_expire_seconds // 60)
        body = f"Your NAADAMAYA code is {code}. It expires in {minutes} minutes. Do not share it."
        url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
        token = base64.b64encode(
            f"{settings.twilio_account_sid}:{settings.twilio_auth_token}".encode()
        ).decode()
        _post(
            url,
            data=urllib.parse.urlencode(
                {"To": phone_e164, "From": settings.twilio_from_number, "Body": body}
            ).encode(),
            headers={
                "Authorization": f"Basic {token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )


# ==========================================================
# Factory
# ==========================================================
@lru_cache
def get_otp_provider() -> OtpProvider:
    name = settings.otp_provider.lower()
    if name == "mock":
        if settings.is_production:
            raise ServiceUnavailableError("SMS delivery is not configured.")
        return MockOtpProvider()
    if name == "msg91":
        return Msg91OtpProvider()
    if name == "twilio":
        return TwilioOtpProvider()
    raise ServiceUnavailableError("SMS delivery is not configured.")
