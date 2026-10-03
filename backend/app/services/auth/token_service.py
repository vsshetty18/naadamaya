"""
NAADAMAYA session tokens.

    pair = issue_session(db, user, ip=ip, user_agent=ua)   # after a verified OTP
    pair, user = rotate_session(db, raw_refresh_token)     # POST /auth/refresh
    revoke_session(db, raw_refresh_token)                  # POST /auth/logout
    revoke_all_sessions(db, user_id)                       # logout everywhere, account deletion

A session is a short-lived access token (JWT, never stored) plus a long-lived
refresh token. Only a keyed hash of the refresh token is stored, so a database
leak does not expose usable tokens.

Rotation: every refresh revokes the old token and issues a new one in the same
family. If a token that was already exchanged is presented again, it was
probably stolen, so the WHOLE family is revoked and everyone using it must
sign in again with an OTP.

IMPORTANT: get_db() rolls back when a request raises an error. Revocations
made right before raising must survive, so those paths commit explicitly.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AccountDisabledError, InvalidTokenError, TokenExpiredError
from app.core.logging import get_logger, log_event
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    utcnow,
)
from app.models.enums import UserStatus
from app.models.refresh_token import RefreshToken
from app.models.user import User

log = get_logger("naadamaya.auth.tokens")


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str      # the raw value, shown to the app once and never stored
    expires_in: int         # access token lifetime in seconds
    user_id: uuid.UUID


def _is_usable(user: User | None) -> bool:
    return (
        user is not None
        and user.is_active
        and not user.is_deleted
        and user.status == UserStatus.ACTIVE.value
    )


def _new_refresh_row(
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    *,
    ip: str | None,
    user_agent: str | None,
    device_label: str | None,
) -> tuple[RefreshToken, str]:
    raw = generate_refresh_token()
    row = RefreshToken(
        id=uuid.uuid4(),
        user_id=user_id,
        family_id=family_id,
        token_hash=hash_refresh_token(raw),
        expires_at=utcnow() + timedelta(days=settings.jwt_refresh_expire_days),
        created_ip=(ip or None) and ip[:45],
        user_agent=(user_agent or None) and user_agent[:300],
        device_label=(device_label or None) and device_label[:120],
    )
    return row, raw


def _revoke_family(db: Session, family_id: uuid.UUID) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


# ==========================================================
# Sign in
# ==========================================================
def issue_session(
    db: Session,
    user: User,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
    device_label: str | None = None,
) -> TokenPair:
    """Starts a new session (a new token family) for a user who just passed OTP."""
    row, raw = _new_refresh_row(
        user.id, uuid.uuid4(), ip=ip, user_agent=user_agent, device_label=device_label
    )
    db.add(row)
    db.flush()

    access, expires_in = create_access_token(user.id, user.role)
    return TokenPair(access_token=access, refresh_token=raw, expires_in=expires_in, user_id=user.id)


# ==========================================================
# Refresh (rotation with theft detection)
# ==========================================================
def rotate_session(
    db: Session,
    raw_refresh_token: str,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[TokenPair, User]:
    now = utcnow()

    row = db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(raw_refresh_token))
        .with_for_update()
    )
    if row is None:
        raise InvalidTokenError()

    # An already-exchanged token being used again: treat as theft.
    if row.replaced_by_id is not None:
        _revoke_family(db, row.family_id)
        db.commit()  # must persist even though we raise next
        log_event(log, "refresh_token_reuse_detected", user_id=str(row.user_id))
        raise InvalidTokenError()

    # Logged out or revoked by another action.
    if row.revoked_at is not None:
        raise InvalidTokenError()

    if row.expires_at <= now:
        raise TokenExpiredError()

    user = db.get(User, row.user_id)
    if not _is_usable(user):
        _revoke_family(db, row.family_id)
        db.commit()
        raise AccountDisabledError()

    new_row, raw = _new_refresh_row(
        row.user_id,
        row.family_id,
        ip=ip,
        user_agent=user_agent,
        device_label=row.device_label,
    )
    db.add(new_row)
    db.flush()  # the new row must exist before the old one points at it

    row.revoked_at = now
    row.replaced_by_id = new_row.id
    row.last_used_at = now
    user.last_seen_at = now

    access, expires_in = create_access_token(user.id, user.role)
    pair = TokenPair(access_token=access, refresh_token=raw, expires_in=expires_in, user_id=user.id)
    return pair, user


# ==========================================================
# Logout
# ==========================================================
def revoke_session(db: Session, raw_refresh_token: str | None) -> uuid.UUID | None:
    """
    Ends the session that owns this token (the whole family). Never raises for an
    unknown or already-ended token: logging out must always succeed in the app.
    Returns the user id when a session was found.
    """
    if not raw_refresh_token:
        return None

    row = db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(raw_refresh_token)
        )
    )
    if row is None:
        return None

    _revoke_family(db, row.family_id)
    return row.user_id


def revoke_all_sessions(db: Session, user_id: uuid.UUID) -> None:
    """Ends every session of a user (logout everywhere, account deletion)."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    log_event(log, "all_sessions_revoked", user_id=str(user_id))
