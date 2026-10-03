"""
NAADAMAYA recording schemas (the singer's own takes).

Routes:
    POST /recordings                 multipart upload  -> RecordingResponse
    GET  /recordings                 (filter by song)  -> Page[RecordingResponse]
    GET  /recordings/{recording_id}                    -> RecordingResponse
    DELETE /recordings/{recording_id}                  -> MessageResponse

The upload arrives as multipart form data: the audio file plus `song_id`
and an optional `source` ("upload" or "browser_recording"). The route reads
those form fields directly, so no request schema is needed here.

The same user can submit many recordings for the same song. Each one gets
the next attempt_number and can be analysed independently.

Responses never contain storage keys or file paths. `audio_url` is a
short-lived signed link, or an authenticated API path for local storage.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import APIModel

RecordingSource = Literal["upload", "browser_recording"]


class RecordingResponse(APIModel):
    id: uuid.UUID
    song_id: uuid.UUID
    song_title: str | None = Field(default=None, description="Title of the reference song.")

    attempt_number: int = Field(examples=[1])
    source: str = Field(examples=["upload"])

    original_filename: str | None = Field(default=None, description="Display only.")
    format: str | None = None
    file_size: int | None = None
    duration: float | None = Field(default=None, description="Seconds.")
    sample_rate: int | None = None
    channels: int | None = None
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

    analysis_count: int = Field(
        default=0, description="How many analyses exist for this recording."
    )
    latest_analysis_id: uuid.UUID | None = None
    created_at: datetime
