"""
NAADAMAYA song schemas (reference / original tracks).

Routes:
    POST   /songs/reference   multipart upload     -> SongResponse
    GET    /songs                                  -> Page[SongResponse]
    GET    /songs/{song_id}                         -> SongResponse
    DELETE /songs/{song_id}                         -> MessageResponse

The upload itself arrives as multipart form data (file + text fields), so
the text fields are plain form parameters in the route. SongMetadata below
is the validated version of those fields, built by the route.

Responses never contain storage keys or file paths. `audio_url` is a
short-lived signed link, or an authenticated API path for local storage.
"""

import uuid
from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.common import APIModel
from app.utils.validators import clean_text


class SongMetadata(APIModel):
    """Optional details the singer may add when uploading a reference song."""

    title: str | None = Field(default=None, max_length=200, examples=["Mungaru Maleye"])
    artist: str | None = Field(default=None, max_length=160, examples=["Yograj Bhat"])
    movie: str | None = Field(default=None, max_length=160)
    language: str | None = Field(default=None, max_length=30, examples=["Kannada"])
    genre: str | None = Field(default=None, max_length=60)
    lyricist: str | None = Field(default=None, max_length=160)
    composer: str | None = Field(default=None, max_length=160)
    lyrics: str | None = Field(
        default=None,
        max_length=20000,
        description="Optional. Used for pronunciation analysis when available.",
    )

    @field_validator(
        "title", "artist", "movie", "language", "genre", "lyricist", "composer", mode="before"
    )
    @classmethod
    def _clean_short(cls, v):
        return clean_text(v, max_length=200, field="This field") if isinstance(v, str) else v

    @field_validator("lyrics", mode="before")
    @classmethod
    def _clean_lyrics(cls, v):
        if not isinstance(v, str):
            return v
        text = v.strip()
        return text or None


class SongResponse(APIModel):
    id: uuid.UUID
    title: str
    artist: str | None = None
    movie: str | None = None
    language: str | None = None
    genre: str | None = None
    lyricist: str | None = None
    composer: str | None = None

    source_type: str = Field(examples=["UPLOAD"])
    original_filename: str | None = Field(default=None, description="Display only.")
    format: str | None = None
    file_size: int | None = None
    duration: float | None = Field(default=None, description="Seconds.")
    status: str = Field(examples=["READY"])

    audio_url: str | None = Field(
        default=None,
        description="Short-lived signed link or authenticated API path. Never a storage path.",
    )
    waveform: list[float] = Field(
        default_factory=list, description="Bars 0..1 drawn from the real audio."
    )
    warnings: list[str] = Field(
        default_factory=list, description='Audio quality notes, e.g. "clipping", "very_quiet".'
    )
    has_lyrics: bool = False

    attempt_count: int = Field(default=0, description="How many of YOUR recordings exist for this song.")
    created_at: datetime
