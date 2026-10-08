"""
NAADAMAYA analysis worker (Celery task).

    run_analysis.apply_async(args=[str(analysis_id)], queue=...)

The API reserves the credit and queues this task (see services/analysis/
analysis_service.py, written later). The task:

  1. Claims the analysis (QUEUED -> PROCESSING) under a row lock. If it is
     already PROCESSING, COMPLETED or FAILED it does nothing, so a redelivered
     task (task_acks_late) never runs the work twice.
  2. Runs the pipeline.
  3. On success saves the result and marks COMPLETED.
  4. On failure marks FAILED with a SAFE message and refunds the credit.
     Every failure here is treated as ours, not the singer's: the credit is
     returned (the refund is idempotent per analysis).

Errors shown to users never contain internals: AppError messages are safe by
design, everything else becomes a generic message. Details go to the logs.

A stuck task is stopped by Celery's soft time limit, which raises
SoftTimeLimitExceeded inside the task; it is handled like any other failure.
"""

import uuid

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select

from app.core.database import session_scope
from app.core.exceptions import AppError
from app.core.logging import get_logger, log_event
from app.core.security import utcnow
from app.models.analysis import Analysis
from app.models.enums import AnalysisStage, AnalysisStatus
from app.services.analysis.analysis_pipeline import run_pipeline, save_result
from app.services.credits.credit_service import refund_credit
from app.workers.celery_app import celery_app

log = get_logger("naadamaya.worker")

GENERIC_ERROR = "We could not finish analysing this performance."
TIMEOUT_ERROR = "The analysis took longer than expected."


def _claim(analysis_id: uuid.UUID) -> bool:
    """QUEUED -> PROCESSING under a row lock. False if someone else has it or it is finished."""
    with session_scope() as db:
        analysis = db.scalar(select(Analysis).where(Analysis.id == analysis_id).with_for_update())
        if analysis is None or analysis.is_deleted:
            return False
        if analysis.status != AnalysisStatus.QUEUED.value:
            return False
        analysis.status = AnalysisStatus.PROCESSING.value
        analysis.stage = AnalysisStage.PREPROCESSING.value
        analysis.progress = 5
        analysis.processing_started_at = utcnow()
        return True


def _fail(analysis_id: uuid.UUID, code: str, message: str) -> None:
    """Marks FAILED and returns the credit, in one transaction."""
    with session_scope() as db:
        analysis = db.scalar(select(Analysis).where(Analysis.id == analysis_id).with_for_update())
        if analysis is None or analysis.status == AnalysisStatus.COMPLETED.value:
            return
        analysis.status = AnalysisStatus.FAILED.value
        analysis.error_code = code[:40]
        analysis.error_message = message[:500]
        analysis.completed_at = utcnow()
        if analysis.credit_reserved and not analysis.credit_refunded:
            if refund_credit(db, analysis.user_id, analysis.id):
                analysis.credit_refunded = True
            elif not analysis.credit_refunded:
                # Already refunded by an earlier attempt (unique ledger key), so just record it.
                analysis.credit_refunded = True
    log_event(log, "analysis_failed", analysis_id=str(analysis_id), code=code)


@celery_app.task(name="naadamaya.run_analysis", bind=True, max_retries=0)
def run_analysis(self, analysis_id: str) -> None:
    aid = uuid.UUID(analysis_id)

    if not _claim(aid):
        log.info("analysis %s was not claimable (already handled)", analysis_id)
        return

    log_event(log, "analysis_started", analysis_id=analysis_id)
    try:
        with session_scope() as db:
            analysis = db.get(Analysis, aid)
            result = run_pipeline(db, analysis)
            save_result(db, analysis, result)
    except SoftTimeLimitExceeded:
        _fail(aid, "TIMEOUT", TIMEOUT_ERROR)
    except AppError as exc:
        log.warning("analysis %s failed: %s", analysis_id, exc.code)
        _fail(aid, exc.code, exc.message)
    except Exception:  # noqa: BLE001 - anything unexpected
        log.exception("analysis %s crashed", analysis_id)
        _fail(aid, "ANALYSIS_FAILED", GENERIC_ERROR)
