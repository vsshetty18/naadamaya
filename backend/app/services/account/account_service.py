"""
NAADAMAYA account deletion.

    result = delete_account(db, user)       # DELETE /users/me

What happens, in order, in ONE transaction:
  1. Every session is revoked (refresh tokens), so no device stays signed in.
  2. Everything the user created is removed: analyses (with metrics, sections,
     insights, recommendations, timelines), recordings, songs, the profile.
  3. The phone number is overwritten with a unique placeholder, so the real
     number is free to sign up again later as a brand-new account.
  4. The user row is kept but anonymised and marked DELETED.
  5. Stored audio and the profile photo are deleted AFTER the database
     commit succeeds (see delete_stored_files).

What is KEPT, and why:
  - payments and credit_transactions rows. Financial records must survive for
    legal and accounting reasons (their user_id foreign key is RESTRICT).
    They point to an anonymised user row that no longer holds a phone number.
  - OTP rows for the number are deleted (they only contain a hash and the number).

Deleting files is done after the commit so a database failure never leaves an
account that still exists but has lost its audio. If file deletion fails
afterwards, it is logged for cleanup; the account is already gone.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.core.logging import get_logger, log_event
from app.core.security import utcnow
from app.models.analysis import Analysis
from app.models.enums import SubscriptionStatus, UserStatus
from app.models.otp import OtpCode
from app.models.profile import Profile
from app.models.recording import Recording
from app.models.song import Song
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.user import DeleteAccountResponse
from app.services.auth.token_service import revoke_all_sessions
from app.services.storage.storage_service import get_storage
from app.utils.file_utils import user_prefix
from app.utils.phone import anonymized_phone

log = get_logger("naadamaya.account")


@dataclass(frozen=True)
class DeletionOutcome:
    response: DeleteAccountResponse
    user_id: uuid.UUID


def delete_account(db: Session, user: User) -> DeletionOutcome:
    """Removes the user's data in the database. Call delete_stored_files() after the commit."""
    user_id = user.id
    phone = user.phone_number_normalized

    revoke_all_sessions(db, user_id)

    # Analyses cascade to their metrics, sections, insights, recommendations and timeline.
    db.execute(delete(Analysis).where(Analysis.user_id == user_id))
    db.execute(delete(Recording).where(Recording.user_id == user_id))
    db.execute(delete(Song).where(Song.owner_id == user_id))
    db.execute(delete(Profile).where(Profile.user_id == user_id))
    db.execute(delete(OtpCode).where(OtpCode.phone_number_normalized == phone))

    # The subscription stays (it is a financial record) but is closed.
    db.execute(
        update(Subscription)
        .where(Subscription.user_id == user_id, Subscription.status == SubscriptionStatus.ACTIVE.value)
        .values(status=SubscriptionStatus.CANCELLED.value, cancelled_at=utcnow())
    )

    placeholder = anonymized_phone(user_id)
    user.phone_number = placeholder
    user.phone_number_normalized = placeholder
    user.phone_region = None
    user.phone_verified = False
    user.status = UserStatus.DELETED.value
    user.is_active = False
    user.is_deleted = True
    user.deleted_at = utcnow()
    db.flush()

    log_event(log, "account_deleted", user_id=str(user_id))
    return DeletionOutcome(response=DeleteAccountResponse(), user_id=user_id)


def delete_stored_files(user_id: uuid.UUID) -> None:
    """
    Removes every stored file the user owned (songs, recordings, photo).
    Call this AFTER the database transaction has committed. Never raises.
    """
    try:
        removed = get_storage().delete_prefix(user_prefix(user_id))
        log_event(log, "account_files_deleted", user_id=str(user_id), files=removed)
    except Exception:  # noqa: BLE001
        log.error("could not delete stored files for deleted account %s; needs manual cleanup", user_id)
