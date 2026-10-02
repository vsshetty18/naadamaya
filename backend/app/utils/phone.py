"""
NAADAMAYA phone number helpers.

One phone number = one account, so every number is converted to ONE canonical
form (E.164, e.g. "+919876543210") before it is stored or compared. All of
these inputs give the same result:

    "98765 43210"        "+91 98765 43210"     "919876543210"
    "09876543210"        "+91-98765-43210"     "0091 98765 43210"

India is the default region (DEFAULT_COUNTRY_CODE), but numbers with any
country code work, so international users can be supported later.
"""

from dataclasses import dataclass
import uuid

import phonenumbers
from phonenumbers import PhoneNumberType

from app.core.config import settings
from app.core.exceptions import InvalidPhoneNumberError

MAX_INPUT_LENGTH = 32

# Number kinds that cannot receive an SMS code.
_NOT_SMS_CAPABLE = {
    PhoneNumberType.FIXED_LINE,
    PhoneNumberType.TOLL_FREE,
    PhoneNumberType.PREMIUM_RATE,
    PhoneNumberType.SHARED_COST,
    PhoneNumberType.VOIP,
    PhoneNumberType.PAGER,
    PhoneNumberType.UAN,
    PhoneNumberType.VOICEMAIL,
}


@dataclass(frozen=True)
class NormalizedPhone:
    e164: str            # "+919876543210": stored in the database
    region: str | None   # "IN"
    country_code: int    # 91
    national: str        # "9876543210"


def normalize_phone(raw: str, default_region: str | None = None) -> NormalizedPhone:
    """
    Turns user input into the canonical form.
    Raises InvalidPhoneNumberError for anything that is not a real,
    SMS-capable number.
    """
    if not isinstance(raw, str):
        raise InvalidPhoneNumberError()

    text = raw.strip()
    if not text or len(text) > MAX_INPUT_LENGTH:
        raise InvalidPhoneNumberError()

    region = (default_region or settings.default_country_code).upper()

    try:
        parsed = phonenumbers.parse(text, region)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneNumberError() from exc

    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneNumberError()

    if phonenumbers.number_type(parsed) in _NOT_SMS_CAPABLE:
        raise InvalidPhoneNumberError("Please enter a mobile number that can receive an SMS.")

    return NormalizedPhone(
        e164=phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
        region=phonenumbers.region_code_for_number(parsed),
        country_code=parsed.country_code,
        national=str(parsed.national_number),
    )


def mask_phone(e164: str) -> str:
    """
    "+919876543210" -> "+91 XXXXXXXX10". Safe to show on screen and to log.
    The full number is never logged.
    """
    try:
        parsed = phonenumbers.parse(e164, None)
    except phonenumbers.NumberParseException:
        return "XXXXXXXXXX"

    national = str(parsed.national_number)
    hidden = "X" * max(len(national) - 2, 0)
    return f"+{parsed.country_code} {hidden}{national[-2:]}"


def anonymized_phone(user_id: uuid.UUID) -> str:
    """
    Replacement value written over a deleted account's phone number. It is not
    a valid number, it is unique per user, and it fits the 20-character
    column, so the real number can sign up again later as a brand-new account.
    """
    return f"del{user_id.hex[:16]}"
