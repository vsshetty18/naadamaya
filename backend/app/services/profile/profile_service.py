"""
NAADAMAYA profile service.

    profile  = get_profile(db, user)                      # the Profile row (created if missing)
    response = get_profile_response(db, user)             # ProfileResponse
    response = update_profile(db, user, payload)          # PUT /profile
    response = set_profile_photo(db, user, stream, name, content_type)   # POST /profile/photo
    user_me  = get_user_me(db, user)                      # GET /users/me

Rules:
  - Updates are PARTIAL: only fields the app actually sent change
    (payload.model_fields_set). A field sent as null is cleared.
  - The phone number is never changed here (it is the account identity).
  - A username must be unique. A clash answers 409 CONFLICT.
  - Photos are validated by decoding the real image bytes (not the extension),
    limited in size, stored under the user's own storage prefix, and the old
    photo is deleted. Only a storage KEY is saved, never a URL.
  - The vocal range typed in by the singer is stored with
    vocal_range_source="self_reported".
"""

import io
import uuid
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    FileTooLargeError,
    InvalidAudioError,
    UnsupportedMediaError,
)
from app.core.logging import get_logger, log_event
from app.models.profile import Profile
from app.models.user import User
from app.schemas.profile import ProfileResponse, ProfileUpdate
from app.schemas.user import UserMe
from app.services.storage.base import StorageError
from app.services.storage.storage_service import build_download_url, delete_quietly, get_storage
from app.utils.file_utils import (
    ALLOWED_IMAGE_EXTENSIONS,
    get_extension,
    has_dangerous_extension,
    profile_photo_key,
)

log = get_logger("naadamaya.profile")

MAX_PHOTO_BYTES = 5 * 1024 * 1024
IMAGE_SIGNATURES = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
)


def get_profile(db: Session, user: User) -> Profile:
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if profile is None:  # should not happen (created at sign-up), but never crash
        profile = Profile(user_id=user.id, preferred_languages=[], preferred_genres=[])
        db.add(profile)
        db.flush()
    return profile


def _photo_url(profile: Profile) -> str | None:
    if not profile.profile_photo_key:
        return None
    return build_download_url(profile.profile_photo_key) or f"{settings.api_v1_prefix}/profile/photo"


def _to_response(user: User, profile: Profile) -> ProfileResponse:
    return ProfileResponse(
        id=profile.id,
        user_id=user.id,
        phone_number=user.phone_number_normalized,
        display_name=profile.display_name,
        username=profile.username,
        email=profile.email,
        gender=profile.gender,
        profile_photo_url=_photo_url(profile),
        preferred_language=profile.preferred_language,
        preferred_languages=list(profile.preferred_languages or []),
        preferred_genres=list(profile.preferred_genres or []),
        preferred_music_style=profile.preferred_music_style,
        experience_level=profile.experience_level,
        vocal_range_low=profile.vocal_range_low,
        vocal_range_high=profile.vocal_range_high,
        vocal_range_source=profile.vocal_range_source,
        onboarding_completed=profile.onboarding_completed,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def get_profile_response(db: Session, user: User) -> ProfileResponse:
    return _to_response(user, get_profile(db, user))


def update_profile(db: Session, user: User, payload: ProfileUpdate) -> ProfileResponse:
    profile = get_profile(db, user)
    sent = payload.model_fields_set

    for field in sent:
        value = getattr(payload, field)
        if field in ("preferred_languages", "preferred_genres"):
            value = value or []
        if field == "onboarding_completed":
            if value is None:
                continue
        setattr(profile, field, value)

    if "vocal_range_low" in sent or "vocal_range_high" in sent:
        profile.vocal_range_source = (
            "self_reported" if (profile.vocal_range_low or profile.vocal_range_high) else None
        )

    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        raise ConflictError("That username is already taken.", code="USERNAME_TAKEN") from exc

    log_event(log, "profile_updated", user_id=str(user.id), fields=",".join(sorted(sent)))
    return _to_response(user, profile)


def _detect_image(head: bytes) -> str | None:
    for signature, ext in IMAGE_SIGNATURES:
        if head.startswith(signature):
            return ext
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def set_profile_photo(
    db: Session,
    user: User,
    stream: BinaryIO,
    filename: str | None,
    content_type: str | None,
) -> ProfileResponse:
    if has_dangerous_extension(filename) or get_extension(filename) not in ALLOWED_IMAGE_EXTENSIONS:
        raise UnsupportedMediaError("Please upload a JPG, PNG or WebP image.")

    data = stream.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise FileTooLargeError("This image is too large. The limit is 5 MB.")
    if not data:
        raise InvalidAudioError("This image is empty.")

    ext = _detect_image(data[:16])   # the real content decides, not the name
    if ext is None:
        raise UnsupportedMediaError("This file is not a valid JPG, PNG or WebP image.")

    profile = get_profile(db, user)
    old_key = profile.profile_photo_key
    new_key = profile_photo_key(user.id, ext)
    mime = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[ext]

    try:
        get_storage().put_stream(new_key, io.BytesIO(data), content_type=mime)
    except StorageError as exc:
        log.error("could not store profile photo")
        raise ConflictError("We could not save your photo. Please try again.", code="PHOTO_SAVE_FAILED") from exc

    profile.profile_photo_key = new_key
    db.flush()
    delete_quietly(old_key)

    log_event(log, "profile_photo_updated", user_id=str(user.id))
    return _to_response(user, profile)


def get_user_me(db: Session, user: User) -> UserMe:
    from app.services.subscriptions.subscription_service import get_active_subscription

    profile = get_profile(db, user)
    sub = get_active_subscription(db, user.id)
    return UserMe(
        id=user.id,
        phone_number=user.phone_number_normalized,
        phone_verified=user.phone_verified,
        role=user.role,
        status=user.status,
        display_name=profile.display_name,
        profile_photo_url=_photo_url(profile),
        onboarding_completed=profile.onboarding_completed,
        plan_code=sub.plan.code,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )
