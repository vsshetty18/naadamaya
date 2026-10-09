"""
NAADAMAYA profile routes.

    GET  /profile         the singer profile
    PUT  /profile         partial update (only fields sent are changed)
    POST /profile/photo   upload a profile photo (JPG, PNG or WebP, max 5 MB)
    GET  /profile/photo   stream the photo (used when storage cannot sign links, i.e. local disk)

The phone number is never changed here: it is the account identity.
"""

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.models.user import User
from app.schemas.common import COMMON_ERRORS
from app.schemas.profile import ProfileResponse, ProfileUpdate
from app.services.profile.profile_service import (
    get_profile,
    get_profile_response,
    set_profile_photo,
    update_profile,
)
from app.services.storage.base import StorageError, StorageNotFoundError
from app.services.storage.storage_service import get_storage

router = APIRouter(prefix="/profile", tags=["Profile"])

CHUNK = 1024 * 256
MIME_BY_EXT = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


@router.get(
    "",
    response_model=ProfileResponse,
    summary="My profile",
    responses={401: COMMON_ERRORS[401]},
)
def read_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ProfileResponse:
    return get_profile_response(db, user)


@router.put(
    "",
    response_model=ProfileResponse,
    summary="Update my profile (partial)",
    responses={401: COMMON_ERRORS[401], 409: COMMON_ERRORS[403], 422: COMMON_ERRORS[422]},
)
def write_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileResponse:
    return update_profile(db, user, payload)


@router.post(
    "/photo",
    response_model=ProfileResponse,
    summary="Upload a profile photo",
    responses={401: COMMON_ERRORS[401], 422: COMMON_ERRORS[422]},
)
def upload_photo(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileResponse:
    return set_profile_photo(db, user, file.file, file.filename, file.content_type)


@router.get(
    "/photo",
    summary="My profile photo (image bytes)",
    responses={401: COMMON_ERRORS[401], 404: COMMON_ERRORS[404]},
)
def read_photo(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StreamingResponse:
    key = get_profile(db, user).profile_photo_key
    if not key:
        raise NotFoundError("You have not added a photo yet.")
    try:
        stream = get_storage().open(key)
    except (StorageNotFoundError, StorageError) as exc:
        raise NotFoundError("We could not find your photo.") from exc

    def chunks():
        try:
            while data := stream.read(CHUNK):
                yield data
        finally:
            stream.close()

    ext = key.rsplit(".", 1)[-1].lower()
    return StreamingResponse(
        chunks(),
        media_type=MIME_BY_EXT.get(ext, "application/octet-stream"),
        headers={"Cache-Control": "private, max-age=300"},
    )
