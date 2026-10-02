"""
NAADAMAYA songs (reference / original tracks).

For the MVP there is no global song catalogue. A song is created when a
singer uploads an original/reference track, and it belongs to that user:
`owner_id` is set and every read checks it, so one user can never see another
user's uploaded reference.

`owner_id` is nullable only so a future catalogue (source_type=CATALOG) can
hold songs that belong to nobody and are shared.

The reference audio itself is stored through the storage abstraction.
We keep the storage KEY here (never a public URL or raw path). The API turns
the key into a short-lived signed URL when it is needed.

Two versions of the audio are kept:
  - original file: exactly what the user uploaded, never modified
  - processed file: standardised copy (mono, fixed sample rate) for analysis
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import RecordingStatus, SourceType


class Song(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "songs"

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    artist: Mapped[str | None] = mapped_column(String(160), nullable=True)
    movie: Mapped[str | None] = mapped_column(String(160), nullable=True)
    language: Mapped[str | None] = mapped_column(String(30), nullable=True)
    genre: Mapped[str | None] = mapped_column(String(60), nullable=True)
    lyricist: Mapped[str | None] = mapped_column(String(160), nullable=True)
    composer: Mapped[str | None] = mapped_column(String(160), nullable=True)

    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default=SourceType.UPLOAD.value)

    # ---- Reference audio (storage keys, never public paths) ----
    original_file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    processed_file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)  # display only
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)  # seconds
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=RecordingStatus.READY.value)

    # Optional lyrics/transcript used by pronunciation analysis when available.
    lyrics: Mapped[str | None] = mapped_column(String, nullable=True)

    # Cached features and anything else the engine learns about the song
    # (tempo, key, vocal range, difficulty). Used later for recommendations.
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_songs_owner_id_created_at", "owner_id", "created_at"),
        Index("ix_songs_title", "title"),
    )
