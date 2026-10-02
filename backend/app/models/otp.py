"""
NAADAMAYA one-time passwords.

An OTP is NEVER stored in plaintext. Only `code_hash` (HMAC-SHA256 keyed with
TOKEN_HASH_SECRET, see core/security.py) is saved.

Rules the OTP service enforces using these columns:
  - Only one live OTP per phone number and purpose: requesting a new one
    sets `invalidated_at` on the previous one.
  - `expires_at` limits how long a code can be used.
  - `attempt_count` is increased on every wrong guess. After the maximum the
    OTP is dead, which stops brute-forcing a 6-digit code.
  - `verified_at` is set on success, so a code can never be used twice.
  - `requested_ip` supports per-IP abuse limits and suspicious-activity logs.

Rows are short-lived. A cleanup job can delete rows older than a day.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin
from app.models.enums import OtpPurpose
from sqlalchemy import func


class OtpCode(UUIDMixin, Base):
    __tablename__ = "otp_codes"

    # Canonical E.164 number. Not a foreign key: the user may not exist yet (sign-up).
    phone_number_normalized: Mapped[str] = mapped_column(String(20), nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False, default=OtpPurpose.LOGIN.value)

    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    requested_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 fits in 45
    requested_device: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Finding the live code for a number, and counting recent requests.
        Index("ix_otp_codes_phone_purpose_created", "phone_number_normalized", "purpose", "created_at"),
        Index("ix_otp_codes_requested_ip_created", "requested_ip", "created_at"),
        Index("ix_otp_codes_expires_at", "expires_at"),
    )
