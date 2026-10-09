"""
NAADAMAYA report routes.

    GET    /reports/{analysis_id}    the finished comparison report
    DELETE /reports/{analysis_id}    delete this analysis and its report

Ownership is checked inside report_generator.get_report: someone else's,
deleted or missing analyses all answer "not found".

A report that is still queued or processing answers 409 REPORT_NOT_READY. The
app should poll /analysis/{id}/status first and open the report only when the
status is COMPLETED.

Deleting removes the analysis and everything attached to it (metrics,
sections, insights, recommendations, pitch data). The user's recordings and
songs are NOT touched. A running analysis cannot be deleted. Credits are not
returned for a deleted report: the analysis was done.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import ConflictError
from app.core.logging import get_logger, log_event
from app.models.enums import AnalysisStatus
from app.models.user import User
from app.schemas.common import COMMON_ERRORS, MessageResponse
from app.schemas.report import ReportResponse
from app.services.analysis.analysis_service import get_owned_analysis
from app.services.analysis.report_generator import get_report

log = get_logger("naadamaya.reports")

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get(
    "/{analysis_id}",
    response_model=ReportResponse,
    summary="The comparison report",
    description=(
        "Only measured metrics appear in `metrics`. Anything that could not be measured is listed in "
        "`unavailable_metrics` with a reason. `is_simulated` is true for demo (mock) results."
    ),
    responses={
        401: COMMON_ERRORS[401],
        404: COMMON_ERRORS[404],
        409: {"description": "REPORT_NOT_READY: the analysis has not finished."},
    },
)
def read_report(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportResponse:
    return get_report(db, user.id, analysis_id)


@router.delete(
    "/{analysis_id}",
    response_model=MessageResponse,
    summary="Delete a report",
    responses={401: COMMON_ERRORS[401], 404: COMMON_ERRORS[404], 409: {"description": "Still running."}},
)
def delete_report(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    analysis = get_owned_analysis(db, user.id, analysis_id)
    if analysis.status in (AnalysisStatus.QUEUED.value, AnalysisStatus.PROCESSING.value):
        raise ConflictError(
            "This analysis is still running. Please try again when it finishes.",
            code="ANALYSIS_IN_PROGRESS",
        )
    db.delete(analysis)   # metrics, sections, insights, recommendations, timeline cascade
    log_event(log, "report_deleted", user_id=str(user.id), analysis_id=str(analysis_id))
    return MessageResponse(message="Report deleted.")
