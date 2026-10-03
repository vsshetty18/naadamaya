"""
NAADAMAYA sign-in.

    sent   = send_login_otp(db, raw_phone, ip=ip, device=device)
    result = sign_in_with_otp(db, raw_phone, otp, ip=ip, user_agent=ua)

One verified phone number = one account. The first successful OTP for a
number creates the account (User + empty Profile + FREE subscription).
Every later OTP for that number signs in to the SAME account.

Uniqueness is enforced by the database (unique phone_number_normalized).
Account creation runs inside a savepoint: if two requests race and the
database rejects the second insert, that request simply loads the account the
first one created instead of failing or making a duplicate.

Sign-up and login use the same OTP purpose (LOGIN), because the user does not
choose between them: the phone number decides.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AccountDisabledError, AuthRequiredError
from app.core.logging import get_logger, log_event
from app.core.security import utcnow
from app.models.enums import OtpPurpose, UserRole, UserStatus
from app.models.profile import Profile
from app.models.user import User
from app.schemas.auth import AuthUser
from app.services.auth.token_service import TokenPair, issue_session
from app.services.otp.otp_service import OtpSendResult, request_otp, verify_otp
from app.utils.phone import NormalizedPhone, mask_phone

log = get_logger("naadamaya.auth")


@dataclass(frozen=True)
class SignInResult:
    is_new_user: bool
    tokens: TokenPair
    user: AuthUser


# ==========================================================
# Helpers
# ==========================================================
def is_usable(user: User | None) -> bool:
    return (
        user is not None
        and user.is_active
        and not user.is_deleted
        and user.status == UserStatus.ACTIVE.value
    )


def build_auth_user(user: User) -> AuthUser:
    profile = user.profile
    return AuthUser(
        id=user.id,
        phone_number=user.phone_number_normalized,
        phone_verified=user.phone_verified,
        role=user.role,
        status=user.status,
        display_name=profile.display_name if profile else None,
        onboarding_completed=bool(profile.onboarding_completed) if profile else False,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def get_user_by_phone(db: Session, phone_e164: str) -> User | None:
    return db.scalar(select(User).where(User.phone_number_normalized == phone_e164))


def get_user_by_id(db: Session, user_id) -> User | None:
    return db.get(User, user_id)


def _create_user(db: Session, phone: NormalizedPhone) -> tuple[User, bool]:
    """
    Creates the account, or returns the existing one if another request
    created it first. Returns (user, created).
    """
    try:
        with db.begin_nested():  # savepoint: a duplicate only undoes this block
            user = User(
                phone_number=phone.e164,
                phone_number_normalized=phone.e164,
                phone_region=phone.region,
                phone_verified=True,
                status=UserStatus.ACTIVE.value,
                role=UserRole.USER.value,
                is_active=True,
                is_deleted=False,
            )
            db.add(user)
            db.flush()
            db.add(Profile(user_id=user.id, preferred_languages=[], preferred_genres=[]))
            db.flush()
        return user, True
    except IntegrityError:
        existing = get_user_by_phone(db, phone.e164)
        if existing is None:  # a different constraint failed: a real bug, not a race
            raise
        return existing, False


# ==========================================================
# Send OTP
# ==========================================================
def send_login_otp(
    db: Session,
    raw_phone: str,
    *,
    ip: str | None = None,
    device: str | None = None,
) -> OtpSendResult:
    return request_otp(db, raw_phone, purpose=OtpPurpose.LOGIN, ip=ip, device=device)


# ==========================================================
# Verify OTP and sign in
# ==========================================================
def sign_in_with_otp(
    db: Session,
    raw_phone: str,
    otp: str,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
    device_label: str | None = None,
) -> SignInResult:
    phone = verify_otp(db, raw_phone, otp, purpose=OtpPurpose.LOGIN)

    user = get_user_by_phone(db, phone.e164)
    created = False

    if user is None:
        user, created = _create_user(db, phone)

    if not is_usable(user):
        log_event(log, "login_blocked", user_id=str(user.id), status=user.status)
        raise AccountDisabledError()

    if created:
        # Every account starts on the FREE plan with its first credit allowance.
        # ensure_free_subscription is idempotent (written with the subscription service).
        from app.services.subscriptions.subscription_service import ensure_free_subscription

        ensure_free_subscription(db, user)
        log_event(log, "user_registered", user_id=str(user.id), phone=mask_phone(phone.e164))

    now = utcnow()
    user.phone_verified = True
    user.last_login_at = now
    user.last_seen_at = now

    tokens = issue_session(db, user, ip=ip, user_agent=user_agent, device_label=device_label)
    db.flush()

    log_event(log, "login_success", user_id=str(user.id), new_user=created)
    return SignInResult(is_new_user=created, tokens=tokens, user=build_auth_user(user))


def require_user(db: Session, user_id) -> User:
    """Loads a signed-in user and checks the account is still allowed to act."""
    user = get_user_by_id(db, user_id)
    if user is None:
        raise AuthRequiredError("Your session is not valid. Please sign in again.")
    if not is_usable(user):
        raise AccountDisabledError()
    return user
