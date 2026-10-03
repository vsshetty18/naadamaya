"""
NAADAMAYA audio ingestion.

One function turns an upload into stored, analysis-ready audio:

    stored = ingest_audio(
        file.file, file.filename, file.content_type,
        original_key_for=lambda ext: song_original_key(user.id, song_id, ext),
        processed_key_for=lambda: song_processed_key(user.id, song_id),
    )

Steps (each one is a separate module, so any can be replaced):
  1. validation.validated_upload   size limit, real content check, duration
  2. preprocessing.prepared_audio  mono WAV at the analysis sample rate,
                                   loudness, silence, quality warnings
  3. storage                       the ORIGINAL file and the PROCESSED WAV are
                                   stored under separate keys

The original is stored exactly as uploaded and never modified.

Keys are passed in as functions because the original's extension is only known
after validation. Both come from utils/file_utils.py, never from user input.

If anything fails after a file has been stored, the stored files are removed,
so a failed upload leaves nothing behind.

This is synchronous and CPU-heavy. The routes that call it are plain `def`
routes, which FastAPI runs in a worker thread, so they do not block other
requests.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import BinaryIO

from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger, log_event
from app.services.audio.preprocessing import prepared_audio
from app.services.audio.validation import validated_upload
from app.services.storage.base import StorageError
from app.services.storage.storage_service import delete_quietly, get_storage
from app.utils.file_utils import guess_mime, sanitize_display_name

log = get_logger("naadamaya.audio")


@dataclass(frozen=True)
class StoredAudio:
    """Everything the song and recording tables need, plus data for the report."""

    original_file_key: str
    processed_file_key: str
    original_filename: str          # cleaned, for display only
    file_size: int                  # bytes of the original upload
    format: str                     # whitelisted extension, e.g. "m4a"
    duration: float                 # seconds, measured on the processed audio
    sample_rate: int | None         # of the ORIGINAL file
    channels: int | None            # of the ORIGINAL file
    metadata: dict                  # preprocessing measurements (JSON-safe)
    warnings: list[str]             # e.g. ["clipping", "very_quiet"]
    waveform: list[float]           # bars for the Report player, from real audio


def ingest_audio(
    stream: BinaryIO,
    filename: str | None,
    content_type: str | None,
    *,
    original_key_for: Callable[[str], str],
    processed_key_for: Callable[[], str],
    max_bytes: int | None = None,
) -> StoredAudio:
    """
    Validates, preprocesses and stores one uploaded audio file.
    Raises InvalidAudioError, UnsupportedMediaError or FileTooLargeError for bad
    files, and ServiceUnavailableError if storage fails.
    """
    storage = get_storage()
    stored_keys: list[str] = []

    try:
        with validated_upload(stream, filename, content_type, max_bytes) as upload:
            with prepared_audio(upload.path) as audio:
                original_key = original_key_for(upload.extension)
                processed_key = processed_key_for()

                mime = upload.content_type or guess_mime(filename) or "application/octet-stream"
                original = storage.put_file(original_key, upload.path, content_type=mime)
                stored_keys.append(original_key)

                storage.put_file(processed_key, audio.wav_path, content_type="audio/wav")
                stored_keys.append(processed_key)

                result = StoredAudio(
                    original_file_key=original_key,
                    processed_file_key=processed_key,
                    original_filename=sanitize_display_name(filename),
                    file_size=original.size,
                    format=upload.extension,
                    duration=round(audio.duration, 3),
                    sample_rate=upload.info.sample_rate,
                    channels=upload.info.channels,
                    metadata=audio.metadata,
                    warnings=list(audio.warnings),
                    waveform=audio.waveform(),
                )

        log_event(
            log,
            "audio_ingested",
            format=result.format,
            duration=result.duration,
            size=result.file_size,
            warnings=",".join(result.warnings) or "none",
        )
        return result

    except StorageError as exc:
        log.error("storage failed while saving audio")
        delete_quietly(*stored_keys)
        raise ServiceUnavailableError("We could not save your audio. Please try again.") from exc
    except Exception:
        # Validation errors and anything unexpected: remove whatever was stored.
        delete_quietly(*stored_keys)
        raise
