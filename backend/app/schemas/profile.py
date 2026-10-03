"""
NAADAMAYA profile schemas.

Routes:
    GET  /profile         -> ProfileResponse
    PUT  /profile         ProfileUpdate -> ProfileResponse
    POST /profile/photo   (multipart image) -> ProfileResponse

Every field is optional, because onboarding is progressive: OTP sign-in
creates an empty profile and the singer fills in whatever they choose.

ProfileUpdate is a partial update: only the fields the app sends are changed.
A field sent as null (or empty) is cleared. A field that is not sent is left
alone. The service uses `model_fields_set` to tell the two apart.

All text is cleaned by utils/validators.py, so the rules live in one place.
"""

import uuid
from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.common import APIModel
from app.utils.validators import (
    EXPERIENCE_LEVELS,
    GENDERS,
    clean_choice,
    clean_display_name,
    clean_email,
    clean_note,
    clean_string_list,
    clean_text,
    clean_username,
)


class ProfileUpdate(APIModel):
    display_name: str | None = Field(default=None, max_length=120, examples=["V S Vighnesh"])
    username: str | None = Field(default=None, max_length=40, examples=["vighnesh"])
    email: str | None = Field(default=None, max_length=254, examples=["vighnesh@example.com"])
    gender: str | None = Field(default=None, examples=["prefer_not_to_say"])

    preferred_language: str | None = Field(default=None, max_length=30, examples=["English"])
    preferred_languages: list[str] | None = Field(default=None, examples=[["Kannada", "Hindi"]])
    preferred_genres: list[str] | None = Field(default=None, examples=[["Devotional", "Light classical"]])
    preferred_music_style: str | None = Field(default=None, max_length=40)
    experience_level: str | None = Field(default=None, examples=["intermediate"])

    vocal_range_low: str | None = Field(default=None, examples=["C3"])
    vocal_range_high: str | None = Field(default=None, examples=["A4"])

    # Set to true when the singer finishes (or skips) the onboarding screen.
    onboarding_completed: bool | None = None

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, v):
        return clean_display_name(v)

    @field_validator("username")
    @classmethod
    def _username(cls, v):
        return clean_username(v)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return clean_email(v)

    @field_validator("gender")
    @classmethod
    def _gender(cls, v):
        return clean_choice(v, GENDERS, "Gender")

    @field_validator("experience_level")
    @classmethod
    def _experience(cls, v):
        return clean_choice(v, EXPERIENCE_LEVELS, "Experience level")

    @field_validator("preferred_language", "preferred_music_style")
    @classmethod
    def _short_text(cls, v):
        return clean_text(v, max_length=40, field="This field")

    @field_validator("preferred_languages")
    @classmethod
    def _languages(cls, v):
        return None if v is None else clean_string_list(v, "Languages")

    @field_validator("preferred_genres")
    @classmethod
    def _genres(cls, v):
        return None if v is None else clean_string_list(v, "Genres")

    @field_validator("vocal_range_low")
    @classmethod
    def _low(cls, v):
        return clean_note(v, "Lowest note")

    @field_validator("vocal_range_high")
    @classmethod
    def _high(cls, v):
        return clean_note(v, "Highest note")


class ProfileResponse(APIModel):
    id: uuid.UUID
    user_id: uuid.UUID
    phone_number: str = Field(examples=["+919876543210"])
    display_name: str | None = None
    username: str | None = None
    email: str | None = None
    gender: str | None = None

    profile_photo_url: str | None = Field(
        default=None,
        description="Short-lived signed link or authenticated API path. Never a storage path.",
    )

    preferred_language: str | None = None
    preferred_languages: list[str] = Field(default_factory=list)
    preferred_genres: list[str] = Field(default_factory=list)
    preferred_music_style: str | None = None
    experience_level: str | None = None

    vocal_range_low: str | None = None
    vocal_range_high: str | None = None
    vocal_range_source: str | None = Field(
        default=None, description='"self_reported" now; "measured" once derived from recordings.'
    )

    onboarding_completed: bool = False
    created_at: datetime
    updated_at: datetime
