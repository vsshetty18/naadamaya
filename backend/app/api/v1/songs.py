"""
NAADAMAYA song routes (reference / original tracks).

    POST   /songs/reference       upload a reference song (multipart)
    GET    /songs                 my songs (paginated)
    GET    /songs/{song_id}       one song
    GET    /songs/{song_id}/audio the original audio (used when storage cannot sign links)
    DELETE /songs/{song_id}       delete the song, its recordings and its reports

Rules:
  - Every query checks ownership. Someone else's song answers "not found".
  - Uploads go through ingest_audio: size limit, real content check with
    FFmpeg, duration limits, a processed mono WAV, and the original kept
    untouched. Keys are generated, never taken from the filename.
  - The preprocessing measurements (quality warnings, waveform bars) are saved
    in song.metadata_, where the analysis pipeline and the report read them.
  - Deleting is permanent: the database rows go first (recordings, analyses
    and reports cascade), and the stored files are removed after the commit.
    A song with an analysis still running cannot be deleted.

Not built yet: HTTP Range support on the audio route, so seeking in a
streamed local file may be limited. S3/R2 signed links support it natively.
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger, log_event
from app.models.analysis import Analysis
from app.models.enums import AnalysisStatus, SourceType
from app.models.recording import Recording
from app.models.song import Song
from app.models.user import User
from app.schemas.common import COMMON_ERRORS, MessageResponse, Page, PageParams
from app.schemas.song import SongMetadata, SongResponse
from app.services.audio.audio_service import ingest_audio
from app.services.storage.base import StorageError, StorageNotFoundError
from app.services.storage.storage_service import build_download_url, delete_quietly, get_storage
from app.utils.file_utils import sanitize_display_name, song_original_key, song_processed_key

log = get_logger("naadamaya.songs")

router = APIRouter(prefix="/songs", tags=["Songs"])

CHUNK = 1024 * 256
MIME_BY_EXT = {
    "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4", "aac": "audio/aac",
    "flac": "audio/flac", "ogg": "audio/ogg", "webm": "audio/webm", "mp4": "audio/mp4",
}


# ==========================================================
# Helpers (recordings.py imports get_readable_song)
# ==========================================================
def get_readable_song(db: Session, user_id: uuid.UUID, song_id: uuid.UUID) -> Song:
    """A song this user may use: their own, or a shared catalogue song (no owner)."""
    song = db.get(Song, song_id)
    if song is None or song.is_deleted or (song.owner_id is not None and song.owner_id != user_id):
        raise NotFoundError("We could not find that song.")
    return song


def _get_owned_song(db: Session, user_id: uuid.UUID, song_id: uuid.UUID) -> Song:
    """Only the owner may delete."""
    song = db.get(Song, song_id)
    if song is None or song.is_deleted or song.owner_id != user_id:
        raise NotFoundError("We could not find that song.")
    return song


def _audio_url(song: Song) -> str | None:
    if not song.original_file_key:
        return None
    return build_download_url(song.original_file_key, song.original_filename) or (
        f"{settings.api_v1_prefix}/songs/{song.id}/audio"
    )


def _to_response(song: Song, attempt_count: int) -> SongResponse:
    meta = song.metadata_ or {}
    return SongResponse(
        id=song.id,
        title=song.title,
        artist=song.artist,
        movie=song.movie,
        language=song.language,
        genre=song.genre,
        lyricist=song.lyricist,
        composer=song.composer,
        source_type=song.source_type,
        original_filename=song.original_filename,
        format=song.format,
        file_size=song.file_size,
        duration=song.duration,
        status=song.status,
        audio_url=_audio_url(song),
        waveform=list(meta.get("waveform") or []),
        warnings=list(meta.get("warnings") or []),
        has_lyrics=bool(song.lyrics),
        attempt_count=attempt_count,
        created_at=song.created_at,
    )


def _attempt_count(db: Session, user_id: uuid.UUID, song_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count()).select_from(Recording).where(
                Recording.user_id == user_id,
                Recording.song_id == song_id,
                Recording.is_deleted.is_(False),
            )
        )
        or 0
    )


# ==========================================================
# Upload
# ==========================================================
@router.post(
    "/reference",
    response_model=SongResponse,
    status_code=201,
    summary="Upload a reference (original) song",
    description="Multipart form: `file` plus optional title, artist, movie, language, genre, lyricist, composer, lyrics.",
    responses={401: COMMON_ERRORS[401], 422: COMMON_ERRORS[422], 429: COMMON_ERRORS[429]},
)
def upload_reference(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    artist: str | None = Form(default=None),
    movie: str | None = Form(default=None),
    language: str | None = Form(default=None),
    genre: str | None = Form(default=None),
    lyricist: str | None = Form(default=None),
    composer: str | None = Form(default=None),
    lyrics: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SongResponse:
    meta = SongMetadata(
        title=title, artist=artist, movie=movie, language=language,
        genre=genre, lyricist=lyricist, composer=composer, lyrics=lyrics,
    )

    song_id = uuid.uuid4()
    stored = ingest_audio(
        file.file,
        file.filename,
        file.content_type,
        original_key_for=lambda ext: song_original_key(user.id, song_id, ext),
        processed_key_for=lambda: song_processed_key(user.id, song_id),
    )

    display_name = sanitize_display_name(file.filename, fallback="Untitled song")
    fallback_title = display_name.rsplit(".", 1)[0][:200] or "Untitled song"

    song = Song(
        id=song_id,
        owner_id=user.id,
        title=meta.title or fallback_title,
        artist=meta.artist,
        movie=meta.movie,
        language=meta.language,
        genre=meta.genre,
        lyricist=meta.lyricist,
        composer=meta.composer,
        lyrics=meta.lyrics,
        source_type=SourceType.UPLOAD.value,
        original_file_key=stored.original_file_key,
        processed_file_key=stored.processed_file_key,
        original_filename=stored.original_filename,
        file_size=stored.file_size,
        format=stored.format,
        duration=stored.duration,
        sample_rate=stored.sample_rate,
        channels=stored.channels,
        metadata_={
            **stored.metadata,
            "warnings": stored.warnings,
            "waveform": stored.waveform,
        },
    )
    try:
        db.add(song)
        db.flush()
    except Exception:
        delete_quietly(stored.original_file_key, stored.processed_file_key)  # no orphan files
        raise

    log_event(log, "song_uploaded", user_id=str(user.id), song_id=str(song.id))
    return _to_response(song, 0)


# ==========================================================
# Read
# ==========================================================
@router.get(
    "",
    response_model=Page[SongResponse],
    summary="My songs",
    responses={401: COMMON_ERRORS[401]},
)
def list_songs(
    params: PageParams = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[SongResponse]:
    where = (Song.owner_id == user.id, Song.is_deleted.is_(False))
    total = db.scalar(select(func.count()).select_from(Song).where(*where)) or 0
    songs = list(
        db.scalars(
            select(Song).where(*where).order_by(Song.created_at.desc()).offset(params.offset).limit(params.limit)
        )
    )
    counts = {}
    if songs:
        counts = dict(
            db.execute(
                select(Recording.song_id, func.count())
                .where(
                    Recording.user_id == user.id,
                    Recording.is_deleted.is_(False),
                    Recording.song_id.in_([s.id for s in songs]),
                )
                .group_by(Recording.song_id)
            ).all()
        )
    return Page.build([_to_response(s, counts.get(s.id, 0)) for s in songs], total, params)


@router.get(
    "/{song_id}",
    response_model=SongResponse,
    summary="One song",
    responses={401: COMMON_ERRORS[401], 404: COMMON_ERRORS[404]},
)
def read_song(
    song_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SongResponse:
    song = get_readable_song(db, user.id, song_id)
    return _to_response(song, _attempt_count(db, user.id, song.id))


@router.get(
    "/{song_id}/audio",
    summary="The original audio (bytes)",
    responses={401: COMMON_ERRORS[401], 404: COMMON_ERRORS[404]},
)
def read_song_audio(
    song_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    song = get_readable_song(db, user.id, song_id)
    if not song.original_file_key:
        raise NotFoundError("This song has no audio.")
    try:
        stream = get_storage().open(song.original_file_key)
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
        media_type=MIME_BY_EXT.get((song.format or "").lower(), "application/octet-stream"),
        headers={"Cache-Control": "private, max-age=300"},
    )


# ==========================================================
# Delete
# ==========================================================
@router.delete(
    "/{song_id}",
    response_model=MessageResponse,
    summary="Delete a song, its recordings and its reports",
    responses={401: COMMON_ERRORS[401], 404: COMMON_ERRORS[404]},
)
def delete_song(
    song_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    song = _get_owned_song(db, user.id, song_id)

    running = db.scalar(
        select(func.count()).select_from(Analysis).where(
            Analysis.song_id == song.id,
            Analysis.status.in_([AnalysisStatus.QUEUED.value, AnalysisStatus.PROCESSING.value]),
        )
    )
    if running:
        raise ConflictError(
            "An analysis for this song is still running. Please try again when it finishes.",
            code="ANALYSIS_IN_PROGRESS",
        )

    recordings = db.execute(
        select(Recording.original_file_key, Recording.processed_file_key).where(Recording.song_id == song.id)
    ).all()
    keys = [song.original_file_key, song.processed_file_key]
    for original, processed in recordings:
        keys.extend([original, processed])

    db.delete(song)   # recordings, analyses and report tables cascade in the database
    db.commit()       # files are deleted only after the rows are really gone
    delete_quietly(*keys)

    log_event(log, "song_deleted", user_id=str(user.id), song_id=str(song_id))
    return MessageResponse(message="Song deleted.")
