"""
NAADAMAYA user account.

The phone number IS the identity: one verified phone number = one account.
This is enforced by a UNIQUE database constraint on phone_number_normalized,
not just by application checks, so two simultaneous sign-ups for the same
number cannot create two accounts.

Authentication identity lives here. Singer details (display name, photo,
language, experience) live in Profile.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import UserRole, UserStatus


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    # Canonical E.164 form, e.g. "+919876543210". Always stored this way.
    phone_number_normalized: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    # Same value kept for display and future formatting needs.
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # ISO region of the number, e.g. "IN". Supports international numbers later.
    phone_region: Mapped[str | None] = mapped_column(String(4), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=UserStatus.ACTIVE.value)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=UserRole.USER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped["Profile"] = relationship(  # noqa: F821
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_users_status", "status"),
        Index("ix_users_created_at", "created_at"),
    )

    def __repr__(self) -> str:  # never print the phone number into logs
        return f"<User id={self.id} status={self.status}>"
