"""
NAADAMAYA file safety helpers.

Uploaded files are untrusted. Rules enforced here:
  - A user-supplied filename is NEVER used as a storage path. Storage keys are
    generated from random UUIDs plus a whitelisted extension.
  - The original filename is cleaned and kept for DISPLAY only.
  - Keys are validated so path traversal ("../", absolute paths, backslashes,
    null bytes) can never reach the storage layer.

Key layout (the same for local disk and S3-compatible storage):

    users/<user_id>/songs/<song_id>/<file_id>-original.<ext>
    users/<user_id>/songs/<song_id>/<file_id>-processed.wav
    users/<user_id>/recordings/<recording_id>/<file_id>-original.<ext>
    users/<user_id>/recordings/<recording_id>/<file_id>-processed.wav
    users/<user_id>/profile/<file_id>.<ext>
"""

import mimetypes
import os
import re
import unicodedata
import uuid

# Extensions we accept for audio, and the MIME types browsers/phones may send.
ALLOWED_AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "aac", "flac", "ogg", "webm", "mp4"}
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

ALLOWED_AUDIO_MIME_PREFIXES = ("audio/",)
# Some browsers label audio-only containers as video/*. Accepted only when the
# extension is also an audio one, and the real content is re-checked with FFmpeg.
ALLOWED_AUDIO_MIME_EXTRA = {"video/mp4", "video/webm", "application/ogg", "application/octet-stream"}
ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}

# Executable and script types that must never be stored, whatever their MIME says.
DANGEROUS_EXTENSIONS = {
    "exe", "dll", "bat", "cmd", "com", "msi", "scr", "sh", "bash", "ps1", "vbs",
    "js", "jar", "py", "php", "pl", "rb", "html", "htm", "svg", "apk", "app",
}

MAX_DISPLAY_NAME_LENGTH = 120

_SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]*$")


def get_extension(filename: str | None) -> str:
    """Lower-case extension without the dot. Only the LAST one counts."""
    if not filename:
        return ""
    return os.path.splitext(os.path.basename(filename.replace("\\", "/")))[1].lstrip(".").lower()


def has_dangerous_extension(filename: str | None) -> bool:
    """True if ANY dot-separated part is dangerous (catches 'song.php.mp3')."""
    if not filename:
        return False
    parts = os.path.basename(filename.replace("\\", "/")).lower().split(".")[1:]
    return any(part in DANGEROUS_EXTENSIONS for part in parts)


def sanitize_display_name(filename: str | None, fallback: str = "audio") -> str:
    """
    A cleaned filename for DISPLAY only (never for storage). Removes folders,
    control characters and anything that could be used for markup injection.
    """
    if not filename:
        return fallback

    name = os.path.basename(filename.replace("\\", "/"))
    name = unicodedata.normalize("NFC", name)
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"|?*\x00')
    name = name.strip(" .")
    if not name:
        return fallback

    if len(name) > MAX_DISPLAY_NAME_LENGTH:
        stem, ext = os.path.splitext(name)
        name = stem[: MAX_DISPLAY_NAME_LENGTH - len(ext)] + ext
    return name


def guess_mime(filename: str | None) -> str | None:
    if not filename:
        return None
    return mimetypes.guess_type(filename)[0]


def is_allowed_audio_mime(mime: str | None) -> bool:
    if not mime:
        return False
    mime = mime.split(";")[0].strip().lower()
    return mime.startswith(ALLOWED_AUDIO_MIME_PREFIXES) or mime in ALLOWED_AUDIO_MIME_EXTRA


# ==========================================================
# Storage keys
# ==========================================================
def _new_file_id() -> str:
    return uuid.uuid4().hex


def song_original_key(user_id: uuid.UUID, song_id: uuid.UUID, ext: str) -> str:
    return f"users/{user_id}/songs/{song_id}/{_new_file_id()}-original.{_safe_ext(ext)}"


def song_processed_key(user_id: uuid.UUID, song_id: uuid.UUID) -> str:
    return f"users/{user_id}/songs/{song_id}/{_new_file_id()}-processed.wav"


def recording_original_key(user_id: uuid.UUID, recording_id: uuid.UUID, ext: str) -> str:
    return f"users/{user_id}/recordings/{recording_id}/{_new_file_id()}-original.{_safe_ext(ext)}"


def recording_processed_key(user_id: uuid.UUID, recording_id: uuid.UUID) -> str:
    return f"users/{user_id}/recordings/{recording_id}/{_new_file_id()}-processed.wav"


def profile_photo_key(user_id: uuid.UUID, ext: str) -> str:
    return f"users/{user_id}/profile/{_new_file_id()}.{_safe_ext(ext)}"


def user_prefix(user_id: uuid.UUID) -> str:
    """Everything a user owns lives under this prefix (used by account deletion)."""
    return f"users/{user_id}/"


def _safe_ext(ext: str) -> str:
    ext = (ext or "").lower().lstrip(".")
    if ext not in ALLOWED_AUDIO_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Unsupported file extension.")
    return ext


def validate_storage_key(key: str) -> str:
    """
    Final guard before any storage read/write/delete. Rejects traversal and
    anything outside the plain 'users/...' layout. Returns the key unchanged.
    """
    if (
        not key
        or len(key) > 500
        or not _SAFE_KEY_RE.match(key)
        or ".." in key
        or "//" in key
        or key.startswith("/")
    ):
        raise ValueError("Unsafe storage key.")
    return key
