"""
NAADAMAYA user schemas.

The sign-in identity (phone number) lives on User. Everything about the
singer (name, photo, language, vocal range) lives in Profile, see
schemas/profile.py.

Routes:
    GET    /users/me    -> UserMe
    DELETE /users/me    -> DeleteAccountResponse

Account deletion requires the caller to confirm by sending the word DELETE,
so a stray tap or a scripted call cannot remove an account by accident.
"""

import uuid
from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.common import APIModel


class UserMe(APIModel):
    """The signed-in user's own account. Never returned to anyone else."""

    id: uuid.UUID
    phone_number: str = Field(examples=["+919876543210"])
    phone_verified: bool
    role: str = Field(examples=["USER"])
    status: str = Field(examples=["ACTIVE"])
    display_name: str | None = None
    profile_photo_url: str | None = Field(
        default=None,
        description="Short-lived signed link, or an authenticated API path. Never a storage path.",
    )
    onboarding_completed: bool = False
    plan_code: str | None = Field(default=None, examples=["FREE"])
    created_at: datetime
    last_login_at: datetime | None = None


class DeleteAccountRequest(APIModel):
    confirm: str = Field(
        description='Must be the word "DELETE" to confirm.',
        examples=["DELETE"],
    )

    @field_validator("confirm")
    @classmethod
    def _must_confirm(cls, value: str) -> str:
        if value.strip().upper() != "DELETE":
            raise ValueError('Type DELETE to confirm.')
        return value


class DeleteAccountResponse(APIModel):
    success: bool = True
    message: str = "Your account has been deleted."
    # Payment records are kept for legal and accounting reasons, unlinked from your identity.
    retained: list[str] = Field(
        default_factory=lambda: ["payment_records"],
        description="What was kept and why, so the app can tell the user honestly.",
    )
