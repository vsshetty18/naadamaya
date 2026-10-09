"""
NAADAMAYA user routes.

    GET    /users/me     the signed-in account (profile and plan joined in)
    DELETE /users/me     delete the account (requires {"confirm": "DELETE"})

Deletion order matters:
  1. the database work runs and is COMMITTED here, explicitly
  2. only then are the stored files (audio, photo) deleted

If the commit fails, nothing is lost: the account still exists with its audio.
get_db() would normally commit after the route returns, which is too late for
step 2, so this route commits itself.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import COMMON_ERRORS
from app.schemas.user import DeleteAccountRequest, DeleteAccountResponse, UserMe
from app.services.account.account_service import delete_account, delete_stored_files
from app.services.profile.profile_service import get_user_me

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserMe,
    summary="The signed-in account",
    responses={401: COMMON_ERRORS[401]},
)
def read_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserMe:
    return get_user_me(db, user)


@router.delete(
    "/me",
    response_model=DeleteAccountResponse,
    summary="Delete my account and data",
    description=(
        "Removes your recordings, songs, reports and profile, signs out every device and frees "
        "your phone number. Payment records are kept (anonymised) for legal and accounting reasons."
    ),
    responses={401: COMMON_ERRORS[401], 422: COMMON_ERRORS[422]},
)
def delete_me(
    payload: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeleteAccountResponse:
    outcome = delete_account(db, user)
    db.commit()                              # the account is gone in the database
    delete_stored_files(outcome.user_id)     # now remove the audio and photo (never raises)
    return outcome.response
