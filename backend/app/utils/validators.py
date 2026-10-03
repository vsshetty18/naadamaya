"""
NAADAMAYA input validators.

Small, reusable checks for text the user types. Pydantic schemas call these,
so the rules live in one place.

Nothing here touches the database or the network.
"""

import re
import unicodedata

from app.core.exceptions import ValidationFailedError

_USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,30}$")
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
_NOTE_RE = re.compile(r"^[A-G][#b]?-?[0-9]$")
_OTP_RE = re.compile(r"^\d+$")

EXPERIENCE_LEVELS = {"beginner", "intermediate", "advanced", "professional"}
GENDERS = {"female", "male", "non_binary", "prefer_not_to_say"}

MAX_LIST_ITEMS = 12
MAX_LIST_ITEM_LENGTH = 40


def clean_text(value: str | None, *, max_length: int, field: str = "This field") -> str | None:
    """
    Trims, normalises and strips control characters. Empty input becomes None.
    Raises ValidationFailedError if the text is too long.
    """
    if value is None:
        return None
    text = unicodedata.normalize("NFC", value)
    text = "".join(ch for ch in text if ch.isprintable() or ch in " ")
    text = " ".join(text.split())
    if not text:
        return None
    if len(text) > max_length:
        raise ValidationFailedError(f"{field} must be at most {max_length} characters.")
    return text


def clean_display_name(value: str | None) -> str | None:
    text = clean_text(value, max_length=80, field="Name")
    if text and any(ch in text for ch in "<>"):
        raise ValidationFailedError("Name contains characters that are not allowed.")
    return text


def clean_username(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    text = value.strip().lower()
    if not _USERNAME_RE.match(text):
        raise ValidationFailedError(
            "Username must be 3 to 30 characters: letters, numbers, dots or underscores."
        )
    return text


def clean_email(value: str | None) -> str | None:
    """Email is optional and never used to sign in."""
    if value is None or not value.strip():
        return None
    text = value.strip().lower()
    if len(text) > 254 or not _EMAIL_RE.match(text):
        raise ValidationFailedError("Please enter a valid email address.")
    return text


def clean_choice(value: str | None, allowed: set[str], field: str) -> str | None:
    if value is None or not value.strip():
        return None
    text = value.strip().lower()
    if text not in allowed:
        raise ValidationFailedError(f"{field} is not a valid choice.")
    return text


def clean_string_list(values: list[str] | None, field: str) -> list[str]:
    """For preferred languages and genres: trimmed, de-duplicated, length-limited."""
    if not values:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = clean_text(item, max_length=MAX_LIST_ITEM_LENGTH, field=field)
        if text and text.lower() not in seen:
            seen.add(text.lower())
            cleaned.append(text)
    if len(cleaned) > MAX_LIST_ITEMS:
        raise ValidationFailedError(f"{field} can have at most {MAX_LIST_ITEMS} items.")
    return cleaned


def clean_note(value: str | None, field: str = "Note") -> str | None:
    """Scientific pitch notation such as 'C3', 'A#4' or 'Bb2'."""
    if value is None or not value.strip():
        return None
    text = value.strip()
    text = text[0].upper() + text[1:]
    if not _NOTE_RE.match(text):
        raise ValidationFailedError(f"{field} must look like C3, A#4 or Bb2.")
    return text


def validate_otp_format(otp: str, length: int) -> str:
    """Digits only and exactly the configured length. Does not check correctness."""
    text = (otp or "").strip()
    if len(text) != length or not _OTP_RE.match(text):
        raise ValidationFailedError(f"Enter the {length}-digit code.")
    return text
