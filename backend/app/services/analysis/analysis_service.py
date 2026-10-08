"""
NAADAMAYA analysis service (used by the /analysis routes).

    result = start_analysis(db, user, recording_id, song_id=None, idempotency_key=None)
    status = get_status(db, user_id, analysis_id)
    page   = list_analyses(db, user_id, params)
    analysis = get_owned_analysis(db, user_id, analysis_id)
    fail_stuck_analyses(db)          # periodic cleanup

start_analysis never does audio work. It checks ownership, reserves ONE
credit, creates the Analysis row and queues the Celery task, then returns.

Duplicate protection: (user_id, idempotency_key) is unique. Repeating a
request with the same key returns the existing analysis and spends nothing.
When no key is sent, a key is derived from the recording, so double-tapping
REPORT on the same recording within the active window is also harmless.

Ownership: every lookup checks user_id. Someone else's recording, song or
analysis answers "not found".

If queuing fails after the credit was reserved, the analysis is marked FAILED
and the credit is refunded in the same request, so nothing is lost.
"""

import uuid
from datetime import timedelta

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.core.logging import get_logger, log_event
from app.core.security import utcnow
from app.models.analysis import Analysis
from app.models.enums import AnalysisStage, AnalysisStatus
from app.models.recording import Recording
from app.models.song import Song
from app.models.user import User
from app.schemas.analysis import (
    AnalysisStatusResponse,
    AnalysisSummary,
    StartAnalysisResponse,
)
from app.schemas.common import Page, PageParams
from app.services.credits.credit_service import refund_credit, reserve_credit
from app.services.subscriptions.subscription_service import get_active_subscription
from app.workers.analysis_worker import run_analysis
from app.workers.celery_app import ANALYSIS_QUEUE, PRIORITY_QUEUE

log = get_logger("naadamaya.analysis")

STUCK_AFTER = timedelta(minutes=30)
DUPLICATE_WINDOW = timedelta(minutes=10)


def _lock_user_analyses(db: Session, user_id: uuid.UUID) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"analysis:{user_id}"})


def get_owned_analysis(db: Session, user_id: uuid.UUID, analysis_id: uuid.UUID) -> Analysis:
    analysis = db.get(Analysis, analysis_id)
    if analysis is None or analysis.user_id != user_id or analysis.is_deleted:
        raise NotFoundError("We could not find that analysis.")
    return analysis


def _response(analysis: Analysis, remaining: int | None, duplicate: bool) -> StartAnalysisResponse:
    return StartAnalysisResponse(
        analysis_id=analysis.id,
        status=analysis.status,
        stage=analysis.stage,
        progress=analysis.progress,
        attempt_number=analysis.attempt_number,
        is_simulated=analysis.is_simulated,
        credits_remaining=remaining,
        duplicate=duplicate,
    )


def start_analysis(
    db: Session,
    user: User,
    recording_id: uuid.UUID,
    *,
    song_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
) -> StartAnalysisResponse:
    recording = db.get(Recording, recording_id)
    if recording is None or recording.user_id != user.id or recording.is_deleted:
        raise NotFoundError("We could not find that recording.")
    if song_id is not None and song_id != recording.song_id:
        raise NotFoundError("That recording does not belong to this song.")

    song = db.get(Song, recording.song_id)
    if song is None or song.is_deleted or (song.owner_id is not None and song.owner_id != user.id):
        raise NotFoundError("We could not find that song.")

    _lock_user_analyses(db, user.id)

    key = (idempotency_key or f"recording:{recording.id}")[:100]

    existing = db.scalar(
        select(Analysis).where(Analysis.user_id == user.id, Analysis.idempotency_key == key)
    )
    if existing is not None:
        # An explicit key is always honoured. The derived key only blocks
        # accidental repeats: after the window, re-analysing is allowed.
        if idempotency_key or (utcnow() - existing.created_at) < DUPLICATE_WINDOW:
            return _response(existing, None, True)
        key = f"recording:{recording.id}:{uuid.uuid4().hex[:8]}"

    attempt = (
        db.scalar(
            select(func.count()).select_from(Analysis).where(
                Analysis.user_id == user.id, Analysis.song_id == song.id
            )
        )
        or 0
    ) + 1

    analysis = Analysis(
        user_id=user.id,
        song_id=song.id,
        recording_id=recording.id,
        attempt_number=attempt,
        status=AnalysisStatus.QUEUED.value,
        stage=AnalysisStage.QUEUED.value,
        progress=0,
        analysis_version=settings.analysis_version,
        analysis_mode="mock" if settings.use_mock_analysis else "real",
        is_simulated=settings.use_mock_analysis,
        idempotency_key=key,
    )
    db.add(analysis)
    db.flush()

    # Spends one credit (raises USAGE_LIMIT_REACHED and rolls everything back if none left).
    remaining = reserve_credit(db, user.id, analysis.id)
    analysis.credit_reserved = True

    sub = get_active_subscription(db, user.id)
    queue = PRIORITY_QUEUE if (sub.plan.feature_flags or {}).get("priority_processing") else ANALYSIS_QUEUE

    # The worker must see the committed row, so commit BEFORE queuing.
    db.commit()

    try:
        task = run_analysis.apply_async(args=[str(analysis.id)], queue=queue)
        analysis.celery_task_id = str(task.id)[:60]
    except Exception:  # noqa: BLE001 - broker down etc.
        log.exception("could not queue analysis %s", analysis.id)
        analysis.status = AnalysisStatus.FAILED.value
        analysis.error_code = "SERVICE_UNAVAILABLE"
        analysis.error_message = "We could not start the analysis. Please try again."
        analysis.completed_at = utcnow()
        if refund_credit(db, user.id, analysis.id):
            analysis.credit_refunded = True
        db.commit()
        raise ServiceUnavailableError("We could not start the analysis. Your credit was not used.")

    log_event(log, "analysis_queued", analysis_id=str(analysis.id), attempt=attempt, queue=queue)
    return _response(analysis, remaining, False)


def get_status(db: Session, user_id: uuid.UUID, analysis_id: uuid.UUID) -> AnalysisStatusResponse:
    return AnalysisStatusResponse.from_analysis(get_owned_analysis(db, user_id, analysis_id))


def list_analyses(db: Session, user_id: uuid.UUID, params: PageParams) -> Page[AnalysisSummary]:
    where = (Analysis.user_id == user_id, Analysis.is_deleted.is_(False))
    total = db.scalar(select(func.count()).select_from(Analysis).where(*where)) or 0
    rows = db.execute(
        select(Analysis, Song)
        .join(Song, Song.id == Analysis.song_id)
        .where(*where)
        .order_by(Analysis.created_at.desc())
        .offset(params.offset)
        .limit(params.limit)
    ).all()
    items = [
        AnalysisSummary(
            id=a.id, song_id=a.song_id, song_title=s.title, song_artist=s.artist,
            recording_id=a.recording_id, attempt_number=a.attempt_number,
            status=a.status, stage=a.stage, progress=a.progress,
            overall_score=a.overall_score, status_label=a.status_label,
            is_simulated=a.is_simulated, analysis_version=a.analysis_version,
            created_at=a.created_at, completed_at=a.completed_at,
        )
        for a, s in rows
    ]
    return Page.build(items, total, params)


def fail_stuck_analyses(db: Session) -> int:
    """
    Fails analyses stuck in QUEUED/PROCESSING for too long (a worker was killed)
    and refunds their credits. Run periodically (cron or a Celery beat task).
    """
    cutoff = utcnow() - STUCK_AFTER
    stuck = db.scalars(
        select(Analysis)
        .where(
            Analysis.status.in_([AnalysisStatus.QUEUED.value, AnalysisStatus.PROCESSING.value]),
            Analysis.created_at < cutoff,
        )
        .with_for_update(skip_locked=True)
    ).all()
    for a in stuck:
        a.status = AnalysisStatus.FAILED.value
        a.error_code = "TIMEOUT"
        a.error_message = "The analysis took longer than expected."
        a.completed_at = utcnow()
        if a.credit_reserved and not a.credit_refunded and refund_credit(db, a.user_id, a.id):
            a.credit_refunded = True
    if stuck:
        log_event(log, "stuck_analyses_failed", count=len(stuck))
    return len(stuck)
