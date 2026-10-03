"""
NAADAMAYA OTP service.

    result = request_otp(db, raw_phone, ip=ip, device=device)   # sends a code
    phone  = verify_otp(db, raw_phone, code)                    # checks it

Rules enforced here:
  - Phone numbers are normalised to E.164 first (utils/phone.py).
  - Only ONE live code per phone number and purpose: requesting a new code
    invalidates the previous one.
  - Resend cooldown (OTP_RESEND_COOLDOWN_SECONDS).
  - Max requests per phone per hour (OTP_MAX_REQUESTS_PER_HOUR).
  - Max requests per IP per hour (RATE_LIMIT_OTP_PER_IP_PER_HOUR).
  - Codes expire (OTP_EXPIRE_SECONDS) and allow limited wrong guesses
    (OTP_MAX_VERIFY_ATTEMPTS), after which the code is dead.
  - A code works once only (verified_at).
  - Only a keyed hash of the code is stored. The code is never logged.

Concurrency: a per-phone PostgreSQL advisory lock serialises requests for the
same number, so two simultaneous taps cannot both pass the cooldown check.

IMPORTANT: get_db() rolls back when a request raises an error. Wrong-guess
counts must survive that, so verify_otp commits explicitly before raising.
"""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    InvalidOtpError,
    OtpExpiredError,
    OtpRateLimitedError,
)
from app.core.logging import get_logger, log_event
from app.core.security import generate_otp, hash_otp, utcnow, verify_otp_hash
from app.models.enums import OtpPurpose
from app.models.otp import OtpCode
from app.services.otp.providers import get_otp_provider
from app.utils.phone import NormalizedPhone, mask_phone, normalize_phone
from app.utils.validators import validate_otp_format

log = get_logger("naadamaya.otp")


@dataclass(frozen=True)
class OtpSendResult:
    phone: NormalizedPhone
    masked_phone: str
    expires_in: int
    resend_after: int
    development_otp: str | None  # only ever set when settings.otp_dev_mode


def _lock_phone(db: Session, phone_e164: str) -> None:
    """Serialises concurrent requests for one number until the transaction ends."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"otp:{phone_e164}"})


def request_otp(
    db: Session,
    raw_phone: str,
    *,
    purpose: OtpPurpose = OtpPurpose.LOGIN,
    ip: str | None = None,
    device: str | None = None,
) -> OtpSendResult:
    phone = normalize_phone(raw_phone)
    now = utcnow()
    hour_ago = now - timedelta(hours=1)

    _lock_phone(db, phone.e164)

    # ---- resend cooldown ----
    latest = db.scalar(
        select(OtpCode)
        .where(OtpCode.phone_number_normalized == phone.e164, OtpCode.purpose == purpose.value)
        .order_by(OtpCode.created_at.desc())
        .limit(1)
    )
    if latest is not None:
        wait = settings.otp_resend_cooldown_seconds - int((now - latest.created_at).total_seconds())
        if wait > 0:
            raise OtpRateLimitedError(
                f"Please wait {wait} seconds before requesting another code.", retry_after=wait
            )

    # ---- per-phone hourly limit ----
    phone_count = db.scalar(
        select(func.count()).select_from(OtpCode).where(
            OtpCode.phone_number_normalized == phone.e164,
            OtpCode.purpose == purpose.value,
            OtpCode.created_at >= hour_ago,
        )
    ) or 0
    if phone_count >= settings.otp_max_requests_per_hour:
        log_event(log, "otp_phone_limited", phone=mask_phone(phone.e164))
        raise OtpRateLimitedError(retry_after=3600)

    # ---- per-IP hourly limit ----
    if ip:
        ip_count = db.scalar(
            select(func.count()).select_from(OtpCode).where(
                OtpCode.requested_ip == ip, OtpCode.created_at >= hour_ago
            )
        ) or 0
        if ip_count >= settings.rate_limit_otp_per_ip_per_hour:
            log_event(log, "otp_ip_limited", ip=ip)
            raise OtpRateLimitedError(retry_after=3600)

    # ---- invalidate any live code, then create the new one ----
    db.execute(
        text(
            "UPDATE otp_codes SET invalidated_at = :now "
            "WHERE phone_number_normalized = :phone AND purpose = :purpose "
            "AND verified_at IS NULL AND invalidated_at IS NULL"
        ),
        {"now": now, "phone": phone.e164, "purpose": purpose.value},
    )

    code = generate_otp()
    provider = get_otp_provider()
    db.add(
        OtpCode(
            phone_number_normalized=phone.e164,
            purpose=purpose.value,
            code_hash=hash_otp(phone.e164, code),
            expires_at=now + timedelta(seconds=settings.otp_expire_seconds),
            requested_ip=ip,
            requested_device=(device or None) and device[:120],
            provider=provider.name,
        )
    )
    db.flush()

    # If delivery fails this raises and the request rolls back: no dead code is left behind.
    provider.send(phone.e164, code)

    log_event(log, "otp_sent", phone=mask_phone(phone.e164), provider=provider.name)

    return OtpSendResult(
        phone=phone,
        masked_phone=mask_phone(phone.e164),
        expires_in=settings.otp_expire_seconds,
        resend_after=settings.otp_resend_cooldown_seconds,
        development_otp=code if settings.otp_dev_mode else None,
    )


def verify_otp(
    db: Session,
    raw_phone: str,
    otp: str,
    *,
    purpose: OtpPurpose = OtpPurpose.LOGIN,
) -> NormalizedPhone:
    """Returns the normalised phone on success. Raises an AppError otherwise."""
    phone = normalize_phone(raw_phone)
    code = validate_otp_format(otp, settings.otp_length)
    now = utcnow()

    _lock_phone(db, phone.e164)

    record = db.scalar(
        select(OtpCode)
        .where(
            OtpCode.phone_number_normalized == phone.e164,
            OtpCode.purpose == purpose.value,
            OtpCode.verified_at.is_(None),
            OtpCode.invalidated_at.is_(None),
        )
        .order_by(OtpCode.created_at.desc())
        .limit(1)
        .with_for_update()
    )

    if record is None or record.expires_at <= now:
        raise OtpExpiredError()

    if record.attempt_count >= settings.otp_max_verify_attempts:
        record.invalidated_at = now
        db.commit()
        raise OtpRateLimitedError("Too many wrong attempts. Please request a new code.")

    if not verify_otp_hash(phone.e164, code, record.code_hash):
        record.attempt_count += 1
        if record.attempt_count >= settings.otp_max_verify_attempts:
            record.invalidated_at = now
        db.commit()  # must persist even though we raise next
        log_event(log, "otp_wrong_code", phone=mask_phone(phone.e164), attempts=record.attempt_count)
        raise InvalidOtpError()

    record.verified_at = now  # a code can never be used twice
    db.flush()
    log_event(log, "otp_verified", phone=mask_phone(phone.e164))
    return phone
