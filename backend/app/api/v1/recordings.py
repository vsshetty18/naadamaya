"""
NAADAMAYA recording routes (the singer's own takes).

    POST   /recordings                    upload a take for a song (multipart)
    GET    /recordings                    my recordings (paginated, optional ?song_id=)
    GET    /recordings/{recording_id}     one recording
    GET    /recordings/{recording_id}/audio   the audio bytes (local storage)
    DELETE /recordings/{recording_id}     delete it and its reports

Rules:
  - The song must be readable by the user (their own upload).
  - Each upload gets the next attempt number for this user and song. Numbers are
    assigned under a per-user advisory lock and protected by a UNIQUE constraint.
  - Same upload pipeline as songs: FFmpeg validation, original kept untouched,
    processed mono WAV, quality warnings and waveform saved in metadata.
  - Every query checks ownership. Someone else's recording answers "not found".
  - A recording with an analysis still running cannot be deleted.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.api.v1.songs import get_readable_song
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger, log_event
from app.models.analysis import Analysis
from app.models.enums import AnalysisStatus
from app.models.recording import Recording
from app.models.song import Song
from app.models.user import User
from app.schemas.common import COMMON_ERRORS, MessageResponse, Page, PageParams
from app.schemas.recording import RecordingResponse
from app.services.audio.audio_service import ingest_audio
from app.services.storage.base import StorageError, StorageNotFoundError
from app.services.storage.storage_service import build_download_url, delete_quietly, get_storage
from app.utils.file_utils import recording_original_key, recording_processed_key

log = get_logger("naadamaya.recordings")

router = APIRouter(prefix="/recordings", tags=["Recordings"])

CHUNK = 1024 * 256
MIME_BY_EXT = {
    "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4", "aac": "audio/aac",
    "flac": "audio/flac", "ogg": "audio/ogg", "webm": "audio/webm", "mp4": "audio/mp4",
}


def _owned(db: Session, user_id: uuid.UUID, recording_id: uuid.UUID) -> Recording:
    rec = db.get(Recording, recording_id)
    if rec is None or rec.user_id != user_id or rec.is_deleted:
        raise NotFoundError("We could not find that recording.")
    return rec


def _audio_url(rec: Recording) -> str | None:
    if not rec.original_file_key:
        return None
    return build_download_url(rec.original_file_key, rec.original_filename) or (
        f"{settings.api_v1_prefix}/recordings/{rec.id}/audio"
    )


def _to_response(db: Session, rec: Recording, song_title: str | None = None) -> RecordingResponse:
    meta = rec.metadata_ or {}
    if song_title is None:
        song = db.get(Song, rec.song_id)
        song_title = song.title if song else None
    count, latest = db.execute(
        select(func.count(), func.max(Analysis.created_at)).where(
            Analysis.recording_id == rec.id, Analysis.is_deleted.is_(False)
        )
    ).one()
    latest_id = None
    if count:
        latest_id = db.scalar(
            select(Analysis.id)
            .where(Analysis.recording_id == rec.id, Analysis.is_deleted.is_(False))
            .order_by(Analysis.created_at.desc())
            .limit(1)
        )
    return RecordingResponse(
        id=rec.id,
        song_id=rec.song_id,
        song_title=song_title,
        attempt_number=rec.attempt_number,
        source=rec.source,
        original_filename=rec.original_filename,
        format=rec.format,
        file_size=rec.file_size,
        duration=rec.duration,
        sample_rate=rec.sample_rate,
        channels=rec.channels,
        status=rec.status,
        audio_url=_audio_url(rec),
        waveform=list(meta.get("waveform") or []),
        warnings=list(meta.get("warnings") or []),
        analysis_count=int(count or 0),
        latest_analysis_id=latest_id,
        created_at=rec.created_at,
    )


@router.post(
    "",
    response_model=RecordingResponse,
    status_code=201,
    summary="Upload my recording for a song",
    description="Multipart form: `file`, `song_id`, and optional `source` (upload or browser_recording).",
    responses={401: COMMON_ERRORS[401], 404: COMMON_ERRORS[404], 422: COMMON_ERRORS[422], 429: COMMON_ERRORS[429]},
)
def upload_recording(
    file: UploadFile = File(...),
    song_id: uuid.UUID = Form(...),
    source: Literal["upload", "browser_recording"] = Form(default="upload"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecordingResponse:
    song = get_readable_song(db, user.id, song_id)

    recording_id = uuid.uuid4()
    stored = ingest_audio(
        file.file,
        file.filename,
        file.content_type,
        original_key_for=lambda ext: recording_original_key(user.id, recording_id, ext),
        processed_key_for=lambda: recording_processed_key(user.id, recording_id),
    )

    try:
        # Serialise attempt numbering for this user, so two uploads never collide.
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"rec:{user.id}"})
        attempt = (
            db.scalar(
                select(func.coalesce(func.max(Recording.attempt_number), 0)).where(
                    Recording.user_id == user.id, Recording.song_id == song.id
                )
            )
            or 0
        ) + 1

        rec = Recording(
            id=recording_id,
            user_id=user.id,
            song_id=song.id,
            attempt_number=attempt,
            original_file_key=stored.original_file_key,
            processed_file_key=stored.processed_file_key,
            original_filename=stored.original_filename,
            file_size=stored.file_size,
            format=stored.format,
            duration=stored.duration,
            sample_rate=stored.sample_rate,
            channels=stored.channels,
            source=source,
            metadata_={**stored.metadata, "warnings": stored.warnings, "waveform": stored.waveform},
        )
        db.add(rec)
        db.flush()
    except Exception:
        delete_quietly(stored.original_file_key, stored.processed_file_key)  # no orphan files
        raise

    log_event(log, "recording_uploaded", user_id=str(user.id), recording_id=str(rec.id), attempt=attempt)
    return _to_response(db, rec, song.title)


@router.get(
    "",
    response_model=Page[RecordingResponse],
    summary="My recordings",
    responses={401: COMMON_ERRORS[401]},
)
def list_recordings(
    song_id: uuid.UUID | None = Query(default=None, description="Only recordings of this song."),
    params: PageParams = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[RecordingResponse]:
    where = [Recording.user_id == user.id, Recording.is_deleted.is_(False)]
    if song_id is not None:
        where.append(Recording.song_id == song_id)
    total = db.scalar(select(func.count()).select_from(Recording).where(*where)) or 0
    rows = db.scalars(
        select(Recording).where(*where).order_by(Recording.created_at.desc()).offset(params.offset).limit(params.limit)
    ).all()
    return Page.build([_to_response(db, r) for r in rows], total, params)


@router.get(
    "/{recording_id}",
    response_model=RecordingResponse,
    summary="One recording",
    responses={401: COMMON_ERRORS[401], 404: COMMON_ERRORS[404]},
)
def read_recording(
    recording_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecordingResponse:
    return _to_response(db, _owned(db, user.id, recording_id))


@router.get(
    "/{recording_id}/audio",
    summary="My recording audio (bytes)",
    responses={401: COMMON_ERRORS[401], 404: COMMON_ERRORS[404]},
)
def read_recording_audio(
    recording_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    rec = _owned(db, user.id, recording_id)
    if not rec.original_file_key:
        raise NotFoundError("This recording has no audio.")
    try:
        stream = get_storage().open(rec.original_file_key)
    except (StorageNotFoundError, StorageError) as exc:
        raise NotFoundError("We could not find this audio.") from exc

    def chunks():
        try:
            while data := stream.read(CHUNK):
                yield data
        finally:
            stream.close()

    return StreamingResponse(
        chunks(),
        media_type=MIME_BY_EXT.get((rec.format or "").lower(), "application/octet-stream"),
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.delete(
    "/{recording_id}",
    response_model=MessageResponse,
    summary="Delete a recording and its reports",
    responses={401: COMMON_ERRORS[401], 404: COMMON_ERRORS[404]},
)
def delete_recording(
    recording_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    rec = _owned(db, user.id, recording_id)

    running = db.scalar(
        select(func.count()).select_from(Analysis).where(
            Analysis.recording_id == rec.id,
            Analysis.status.in_([AnalysisStatus.QUEUED.value, AnalysisStatus.PROCESSING.value]),
        )
    )
    if running:
        raise ConflictError(
            "An analysis for this recording is still running. Please try again when it finishes.",
            code="ANALYSIS_IN_PROGRESS",
        )

    keys = [rec.original_file_key, rec.processed_file_key]
    db.delete(rec)    # its analyses and reports cascade in the database
    db.commit()       # delete files only after the rows are gone
    delete_quietly(*keys)

    log_event(log, "recording_deleted", user_id=str(user.id), recording_id=str(recording_id))
    return MessageResponse(message="Recording deleted.")
