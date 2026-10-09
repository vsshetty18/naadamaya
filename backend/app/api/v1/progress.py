"""
NAADAMAYA progress routes.

    GET /progress                    overview: totals, averages, streak, weak areas
    GET /progress/history            every completed attempt, newest first (paginated)
    GET /progress/songs/{song_id}    one song: attempts, best, latest, improvement, weak areas

Everything is computed from the signed-in user's own completed analyses
(services/progress/progress_service.py). A new user gets zeros and empty lists.

Route order: the fixed paths (/history, /songs/...) are declared before any
catch-all, so they are matched first.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import COMMON_ERRORS, Page, PageParams
from app.schemas.progress import AttemptEntry, ProgressOverview, SongProgress
from app.services.progress.progress_service import get_overview, get_song_progress, list_history

router = APIRouter(prefix="/progress", tags=["Progress"])


@router.get(
    "",
    response_model=ProgressOverview,
    summary="My progress overview",
    responses={401: COMMON_ERRORS[401]},
)
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ProgressOverview:
    return get_overview(db, user.id)


@router.get(
    "/history",
    response_model=Page[AttemptEntry],
    summary="All my completed attempts",
    responses={401: COMMON_ERRORS[401]},
)
def history(
    params: PageParams = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[AttemptEntry]:
    return list_history(db, user.id, params)


@router.get(
    "/songs/{song_id}",
    response_model=SongProgress,
    summary="Progress on one song",
    responses={401: COMMON_ERRORS[401], 404: COMMON_ERRORS[404]},
)
def song_progress(
    song_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SongProgress:
    return get_song_progress(db, user.id, song_id)
