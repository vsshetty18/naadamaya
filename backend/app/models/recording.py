"""
NAADAMAYA recordings (the singer's own takes).

One row per uploaded or recorded vocal take. The same user can submit many
recordings for the same song: each is an independent attempt that can be
analysed on its own.

Audio is stored through the storage abstraction. Only storage KEYS are kept
here (never public URLs or raw paths). Two versions exist:
  - original file: exactly what the user sent, never modified
  - processed file: standardised copy (mono, fixed sample rate) for analysis

`attempt_number` counts this user's takes for this song (1, 2, 3, ...). It is
assigned inside a transaction and protected by a UNIQUE constraint, so two
simultaneous uploads can never receive the same number.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import RecordingStatus


class Recording(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "recordings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    song_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("songs.id", ondelete="CASCADE"),
        nullable=False,
    )

    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ---- Audio (storage keys, never public paths) ----
    original_file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    processed_file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)  # display only
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)  # seconds
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=RecordingStatus.READY.value)

    # "upload" or "browser_recording" (frontend Record button).
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="upload")

    # Extra measurements from preprocessing (silence trimmed, vocal regions, ...).
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "song_id", "attempt_number", name="uq_recordings_user_song_attempt"),
        Index("ix_recordings_user_id_created_at", "user_id", "created_at"),
        Index("ix_recordings_song_id", "song_id"),
    )
