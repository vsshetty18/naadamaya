"""
NAADAMAYA singer profile.

Kept separate from User on purpose: User is the sign-in identity (phone
number), Profile is everything about the singer. Nothing here is required
during OTP login. Onboarding is progressive, so every field is optional and
`onboarding_completed` records whether the singer finished the setup screen.

Vocal range and the preferred languages/genres are stored here so they can
later feed the song-recommendation feature. Vocal range is entered by the
singer or, in the future, measured from their recordings (`vocal_range_source`
says which).
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Profile(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "profiles"

    # One profile per user, enforced by the database.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    username: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)  # optional, never used to sign in
    profile_photo_key: Mapped[str | None] = mapped_column(String(500), nullable=True)  # storage key, not a URL
    gender: Mapped[str | None] = mapped_column(String(30), nullable=True)

    preferred_language: Mapped[str | None] = mapped_column(String(30), nullable=True)  # app language
    preferred_languages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # languages they sing in
    preferred_genres: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    preferred_music_style: Mapped[str | None] = mapped_column(String(40), nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Notes in scientific pitch notation, e.g. "C3" and "A4".
    vocal_range_low: Mapped[str | None] = mapped_column(String(8), nullable=True)
    vocal_range_high: Mapped[str | None] = mapped_column(String(8), nullable=True)
    vocal_range_source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "self_reported" | "measured"

    onboarding_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped["User"] = relationship(back_populates="profile")  # noqa: F821
