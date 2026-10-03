"""
NAADAMAYA upload validation.

Uploaded files are untrusted. The file extension and the MIME type the client
sends are only a first filter. The real check is FFmpeg/ffprobe reading the
actual content:

  1. Streamed to a temporary file with a hard size limit (a huge upload is
     stopped early, never loaded into memory).
  2. Empty files, dangerous extensions and odd MIME types are rejected.
  3. ffprobe must find a real AUDIO stream in a container we accept.
  4. A short trial decode catches corrupted or truncated files.
  5. Duration must be within MIN_AUDIO_DURATION_SECONDS and
     MAX_AUDIO_DURATION_SECONDS.

Use validated_upload() as a context manager. The temporary file is deleted
when the block ends, even if something fails.

    with validated_upload(file.file, file.filename, file.content_type) as upload:
        upload.path   # local temp file, safe to hand to FFmpeg
        upload.info   # AudioInfo (duration, sample rate, channels, ...)
"""

import json
import os
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import BinaryIO

from app.core.config import settings
from app.core.exceptions import (
    FileTooLargeError,
    InvalidAudioError,
    ServiceUnavailableError,
    UnsupportedMediaError,
)
from app.core.logging import get_logger
from app.utils.file_utils import (
    ALLOWED_AUDIO_EXTENSIONS,
    get_extension,
    has_dangerous_extension,
    is_allowed_audio_mime,
)

log = get_logger("naadamaya.audio.validation")

CHUNK_SIZE = 1024 * 1024
PROBE_TIMEOUT_SECONDS = 20
DECODE_TIMEOUT_SECONDS = 120
TRIAL_DECODE_SECONDS = 10

# Container names ffprobe may report (it can list several, comma-separated).
ALLOWED_CONTAINERS = {
    "mp3", "wav", "flac", "ogg", "aac", "adts",
    "mov", "mp4", "m4a", "matroska", "webm",
}


@dataclass(frozen=True)
class AudioInfo:
    container: str          # e.g. "mov,mp4,m4a,3gp,3g2,mj2"
    codec: str | None       # e.g. "aac", "mp3", "pcm_s16le"
    duration: float         # seconds
    sample_rate: int | None
    channels: int | None
    bit_rate: int | None
    size: int               # bytes


@dataclass(frozen=True)
class ValidatedUpload:
    path: str               # temporary local file (removed after the with-block)
    extension: str          # whitelisted, lower-case, no dot
    info: AudioInfo
    original_filename: str | None
    content_type: str | None


# ==========================================================
# Step 1: stream to a temporary file with a size limit
# ==========================================================
def save_to_temp(stream: BinaryIO, extension: str, max_bytes: int | None = None) -> tuple[str, int]:
    """Copies the upload to a temp file. Stops as soon as the limit is passed."""
    limit = max_bytes or settings.max_upload_size_bytes
    fd, path = tempfile.mkstemp(prefix="naadamaya-upload-", suffix=f".{extension}")
    total = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := stream.read(CHUNK_SIZE):
                total += len(chunk)
                if total > limit:
                    raise FileTooLargeError(
                        f"This file is too large. The limit is {settings.max_upload_size_mb} MB."
                    )
                out.write(chunk)
    except Exception:
        _remove(path)
        raise
    return path, total


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# ==========================================================
# Step 2: ffprobe (what is really inside the file?)
# ==========================================================
def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Runs FFmpeg tools without a shell, with a timeout."""
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False, shell=False
        )
    except FileNotFoundError as exc:
        log.error("ffmpeg/ffprobe is not installed")
        raise ServiceUnavailableError("Audio processing is not available right now.") from exc
    except subprocess.TimeoutExpired as exc:
        raise InvalidAudioError("This audio file took too long to read. It may be damaged.") from exc


def _to_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _to_int(value) -> int | None:
    number = _to_float(value)
    return int(number) if number is not None else None


def probe(path: str, size: int) -> tuple[AudioInfo | None, str]:
    """
    Returns (info, container). `info.duration` may be 0 when the container has no
    length in its header (browser-recorded WebM); the caller then measures it by
    decoding.
    """
    result = _run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", path,
        ],
        PROBE_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise InvalidAudioError()

    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise InvalidAudioError() from exc

    container = str((data.get("format") or {}).get("format_name") or "")
    if not set(container.split(",")) & ALLOWED_CONTAINERS:
        raise UnsupportedMediaError("This file is not a supported audio format.")

    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise InvalidAudioError("No audio was found in this file.")

    fmt = data.get("format") or {}
    duration = _to_float(fmt.get("duration")) or _to_float(audio.get("duration")) or 0.0

    info = AudioInfo(
        container=container,
        codec=audio.get("codec_name"),
        duration=duration,
        sample_rate=_to_int(audio.get("sample_rate")),
        channels=_to_int(audio.get("channels")),
        bit_rate=_to_int(audio.get("bit_rate")) or _to_int(fmt.get("bit_rate")),
        size=size,
    )
    return info, container


# ==========================================================
# Step 3: trial decode (catches corrupted / truncated audio)
# ==========================================================
def decode_check(path: str, limit_seconds: float | None = None) -> float:
    """
    Decodes the audio to nowhere. Returns how many seconds were decoded.
    Raises InvalidAudioError if FFmpeg reports errors.
    """
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-nostats", "-progress", "pipe:1"]
    if limit_seconds:
        cmd += ["-t", str(limit_seconds)]
    cmd += ["-i", path, "-vn", "-f", "null", "-"]

    result = _run(cmd, DECODE_TIMEOUT_SECONDS)
    if result.returncode != 0 or result.stderr.strip():
        raise InvalidAudioError("This audio file seems to be damaged.")

    decoded = 0.0
    for line in result.stdout.splitlines():
        if line.startswith(("out_time_us=", "out_time_ms=")):
            microseconds = _to_float(line.split("=", 1)[1])
            if microseconds is not None and microseconds >= 0:
                decoded = microseconds / 1_000_000.0
    return decoded


# ==========================================================
# The whole check
# ==========================================================
def _check_duration(duration: float) -> None:
    if duration < settings.min_audio_duration_seconds:
        raise InvalidAudioError(
            f"This recording is too short. It must be at least {settings.min_audio_duration_seconds} seconds."
        )
    if duration > settings.max_audio_duration_seconds:
        minutes = settings.max_audio_duration_seconds // 60
        raise InvalidAudioError(f"This recording is too long. The limit is {minutes} minutes.")


@contextmanager
def validated_upload(
    stream: BinaryIO,
    filename: str | None,
    content_type: str | None,
    max_bytes: int | None = None,
) -> Iterator[ValidatedUpload]:
    extension = get_extension(filename)

    if has_dangerous_extension(filename):
        raise UnsupportedMediaError("This file type is not allowed.")
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise UnsupportedMediaError("Please upload an MP3, WAV, M4A, AAC, FLAC or OGG file.")
    if content_type and not is_allowed_audio_mime(content_type):
        raise UnsupportedMediaError("This file does not look like audio.")

    path, size = save_to_temp(stream, extension, max_bytes)
    try:
        if size == 0:
            raise InvalidAudioError("This file is empty.")

        info, _ = probe(path, size)

        if info.duration > 0:
            # Header length is known: a short trial decode is enough.
            decode_check(path, limit_seconds=TRIAL_DECODE_SECONDS)
            duration = info.duration
        else:
            # No length in the header (for example browser-recorded WebM):
            # decode everything once and measure the real length.
            duration = decode_check(path)
            if duration <= 0:
                raise InvalidAudioError("We could not read the length of this audio.")
            info = AudioInfo(
                container=info.container,
                codec=info.codec,
                duration=duration,
                sample_rate=info.sample_rate,
                channels=info.channels,
                bit_rate=info.bit_rate,
                size=info.size,
            )

        _check_duration(duration)

        yield ValidatedUpload(
            path=path,
            extension=extension,
            info=info,
            original_filename=filename,
            content_type=content_type,
        )
    finally:
        _remove(path)
