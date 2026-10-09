"""
NAADAMAYA analysis routes.

    POST /analysis/start                 queue an analysis (spends 1 credit)
    GET  /analysis                       my analyses (paginated)
    GET  /analysis/{id}                  one analysis (summary)
    GET  /analysis/{id}/status           progress (poll this)
    GET  /analysis/{id}/stream           live progress (server-sent events)

Starting never does audio work: it checks ownership and credits, reserves one
credit, queues a job and returns. The app then polls /status or listens to
/stream until status is COMPLETED or FAILED, then fetches /reports/{id}.

Duplicate protection: send an `Idempotency-Key` header (8-100 chars). Repeating
the request returns the existing analysis and spends no second credit.

The SSE stream reads the database on a short interval (no pub/sub needed yet).
It ends when the analysis finishes, fails, or the client disconnects, and it
has a maximum lifetime so connections never pile up. It opens its OWN short
database sessions, because the request session would be held open for the
whole stream.
"""

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.api.v1.deps import get_current_user
from app.core.database import get_db, session_scope
from app.core.exceptions import NotFoundError
from app.models.analysis import Analysis
from app.models.user import User
from app.schemas.analysis import (
    AnalysisStatusResponse,
    AnalysisSummary,
    StartAnalysisRequest,
    StartAnalysisResponse,
)
from app.schemas.common import COMMON_ERRORS, Page, PageParams
from app.services.analysis.analysis_service import (
    get_owned_analysis,
    get_status,
    list_analyses,
    start_analysis,
)

router = APIRouter(prefix="/analysis", tags=["Analysis"])

STREAM_INTERVAL_SECONDS = 1.0
STREAM_MAX_SECONDS = 25 * 60
FINISHED = {"COMPLETED", "FAILED"}


@router.post(
    "/start",
    response_model=StartAnalysisResponse,
    status_code=202,
    summary="Start an analysis",
    description="Spends one credit and queues the job. Returns immediately.",
    responses={
        401: COMMON_ERRORS[401],
        403: {"description": "USAGE_LIMIT_REACHED: no credits left (upgrade_required=true)."},
        404: COMMON_ERRORS[404],
        429: COMMON_ERRORS[429],
    },
)
def start(
    payload: StartAnalysisRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StartAnalysisResponse:
    return start_analysis(
        db,
        user,
        payload.recording_id,
        song_id=payload.song_id,
        idempotency_key=idempotency_key or payload.idempotency_key,
    )


@router.get(
    "",
    response_model=Page[AnalysisSummary],
    summary="My analyses",
    responses={401: COMMON_ERRORS[401]},
)
def list_mine(
    params: PageParams = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[AnalysisSummary]:
    return list_analyses(db, user.id, params)


@router.get(
    "/{analysis_id}/status",
    response_model=AnalysisStatusResponse,
    summary="Progress of an analysis",
    responses={401: COMMON_ERRORS[401], 404: COMMON_ERRORS[404]},
)
def status(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisStatusResponse:
    return get_status(db, user.id, analysis_id)


@router.get(
    "/{analysis_id}/stream",
    summary="Live progress (server-sent events)",
    description="Each event is the same JSON as /status. The stream closes when the analysis ends.",
    responses={401: COMMON_ERRORS[401], 404: COMMON_ERRORS[404]},
)
async def stream(
    analysis_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EventSourceResponse:
    get_owned_analysis(db, user.id, analysis_id)   # ownership checked BEFORE streaming
    user_id = user.id

    def read_status() -> dict | None:
        with session_scope() as session:
            analysis = session.get(Analysis, analysis_id)
            if analysis is None or analysis.user_id != user_id or analysis.is_deleted:
                return None
            return json.loads(AnalysisStatusResponse.from_analysis(analysis).model_dump_json())

    async def events():
        loop = asyncio.get_running_loop()
        waited = 0.0
        last = None
        while waited < STREAM_MAX_SECONDS:
            if await request.is_disconnected():
                return
            data = await loop.run_in_executor(None, read_status)
            if data is None:
                return
            if data != last:
                last = data
                yield {"event": "status", "data": json.dumps(data)}
            if data["status"] in FINISHED:
                return
            await asyncio.sleep(STREAM_INTERVAL_SECONDS)
            waited += STREAM_INTERVAL_SECONDS

    return EventSourceResponse(events())


@router.get(
    "/{analysis_id}",
    response_model=AnalysisSummary,
    summary="One analysis (summary, no report data)",
    responses={401: COMMON_ERRORS[401], 404: COMMON_ERRORS[404]},
)
def read_one(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisSummary:
    from app.models.song import Song

    a = get_owned_analysis(db, user.id, analysis_id)
    song = db.get(Song, a.song_id)
    return AnalysisSummary(
        id=a.id, song_id=a.song_id,
        song_title=song.title if song else None, song_artist=song.artist if song else None,
        recording_id=a.recording_id, attempt_number=a.attempt_number,
        status=a.status, stage=a.stage, progress=a.progress,
        overall_score=a.overall_score, status_label=a.status_label,
        is_simulated=a.is_simulated, analysis_version=a.analysis_version,
        created_at=a.created_at, completed_at=a.completed_at,
    )
