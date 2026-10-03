"""
NAADAMAYA authentication schemas.

Sign-in is phone number + OTP only. There are no passwords and no email login.

Flow:
    POST /auth/send-otp    SendOtpRequest    -> SendOtpResponse
    POST /auth/verify-otp  VerifyOtpRequest  -> VerifyOtpResponse
    POST /auth/refresh     RefreshRequest    -> RefreshResponse
    POST /auth/logout      LogoutRequest     -> MessageResponse
    GET  /auth/me                            -> AuthUser

Phone numbers are accepted in any common format here (length-limited only).
The real normalisation to E.164 happens in the auth service via
utils/phone.py, so there is one place that decides what a valid number is.
"""

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import APIModel


# ==========================================================
# Send OTP
# ==========================================================
class SendOtpRequest(APIModel):
    phone_number: str = Field(
        min_length=5,
        max_length=32,
        examples=["+919876543210", "98765 43210"],
        description="Any common format. It is normalised to E.164 (e.g. +919876543210).",
    )


class SendOtpResponse(APIModel):
    success: bool = True
    message: str = "OTP sent"
    masked_phone: str = Field(examples=["+91 XXXXXXXX10"])
    expires_in: int = Field(description="Seconds until the code expires.", examples=[300])
    resend_after: int = Field(description="Seconds before another code can be requested.", examples=[30])
    # Present ONLY when OTP_MODE=development (never in production), so the
    # frontend can show the fixed development code while no SMS provider exists.
    development_otp: str | None = Field(
        default=None,
        description="Development mode only. Always null in production.",
    )


# ==========================================================
# Verify OTP
# ==========================================================
class VerifyOtpRequest(APIModel):
    phone_number: str = Field(min_length=5, max_length=32)
    otp: str = Field(min_length=4, max_length=10, examples=["123456"])
    # Shown in the user's session list, e.g. "Chrome on Android". Optional.
    device_label: str | None = Field(default=None, max_length=120)


class AuthUser(APIModel):
    """
    The signed-in account as the app needs it right after sign-in.
    Built explicitly by the auth service (it joins the profile), so
    display_name and onboarding_completed are always filled in.
    """

    id: uuid.UUID
    phone_number: str = Field(examples=["+919876543210"])
    phone_verified: bool
    role: str = Field(examples=["USER"])
    status: str = Field(examples=["ACTIVE"])
    display_name: str | None = None
    onboarding_completed: bool = False
    created_at: datetime
    last_login_at: datetime | None = None


class VerifyOtpResponse(APIModel):
    success: bool = True
    is_new_user: bool = Field(description="True when this sign-in created the account.")
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds.", examples=[900])
    user: AuthUser


# ==========================================================
# Refresh and logout
# ==========================================================
class RefreshRequest(APIModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class RefreshResponse(APIModel):
    success: bool = True
    access_token: str
    refresh_token: str = Field(description="A NEW refresh token. The old one stops working.")
    token_type: str = "bearer"
    expires_in: int


class LogoutRequest(APIModel):
    # Optional: with no token the call still succeeds, so logout never fails in the app.
    refresh_token: str | None = Field(default=None, max_length=200)
    all_devices: bool = Field(
        default=False,
        description="Also end every other session of this account.",
    )
