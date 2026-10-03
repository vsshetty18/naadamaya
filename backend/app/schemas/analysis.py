"""
NAADAMAYA analysis schemas (starting an analysis and following its progress).

Routes:
    POST /analysis/start               StartAnalysisRequest -> StartAnalysisResponse
    GET  /analysis                     (paginated)          -> Page[AnalysisSummary]
    GET  /analysis/{analysis_id}                            -> AnalysisSummary
    GET  /analysis/{analysis_id}/status                     -> AnalysisStatusResponse
    GET  /analysis/{analysis_id}/stream (server-sent events)-> AnalysisStatusResponse per event

The finished report (metrics, sections, pitch curves, insights) is NOT here.
It lives in schemas/report.py and is served by GET /reports/{analysis_id}.

Starting an analysis never blocks on the audio work. The route checks
ownership and credits, reserves one credit, queues a job and returns at once.
The app then polls /status (or listens to /stream) until status is COMPLETED
or FAILED.

Duplicate protection: the app sends an `Idempotency-Key` header (or the same
value in the body). Repeating the request with the same key returns the
existing analysis and never reserves a second credit.
"""

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import APIModel

# Text for the progress screen, one entry per stage the worker reports.
STAGE_LABELS: dict[str, str] = {
    "QUEUED": "Queued...",
    "PREPROCESSING": "Preparing your audio...",
    "ALIGNMENT": "Aligning your singing with the original...",
    "PITCH_ANALYSIS": "Analyzing pitch...",
    "RHYTHM_ANALYSIS": "Checking rhythm and timing...",
    "STABILITY_ANALYSIS": "Analyzing vocal stability...",
    "SCORING": "Scoring your performance...",
    "REPORT_GENERATION": "Preparing your report...",
    "COMPLETED": "Analysis complete.",
}

STAGE_ORDER: list[str] = list(STAGE_LABELS.keys())


def stage_label(stage: str | None) -> str:
    return STAGE_LABELS.get(stage or "", "Working...")


# ==========================================================
# Start
# ==========================================================
class StartAnalysisRequest(APIModel):
    recording_id: uuid.UUID = Field(description="Your recording to analyse.")
    song_id: uuid.UUID | None = Field(
        default=None,
        description="Optional. Taken from the recording when omitted. If given it must match.",
    )
    idempotency_key: str | None = Field(
        default=None,
        min_length=8,
        max_length=100,
        description="Same value as the Idempotency-Key header. Prevents double charging.",
    )


class StartAnalysisResponse(APIModel):
    success: bool = True
    analysis_id: uuid.UUID
    status: str = Field(examples=["QUEUED"])
    stage: str = Field(examples=["QUEUED"])
    progress: int = Field(ge=0, le=100)
    attempt_number: int
    is_simulated: bool = Field(
        description="True when ANALYSIS_MODE=mock. Results are then clearly labelled as a demo."
    )
    credits_remaining: int | None = Field(
        default=None, description="Credits left after reserving one for this analysis."
    )
    # True when the same idempotency key was seen before and the existing analysis is returned.
    duplicate: bool = False


# ==========================================================
# Progress
# ==========================================================
class AnalysisErrorInfo(APIModel):
    code: str = Field(examples=["ANALYSIS_FAILED"])
    message: str = Field(description="Safe for users. Never contains internal details.")
    credit_refunded: bool = Field(
        default=False, description="True when the reserved credit was given back."
    )


class AnalysisStatusResponse(APIModel):
    analysis_id: uuid.UUID
    status: str = Field(examples=["PROCESSING"])
    stage: str = Field(examples=["PITCH_ANALYSIS"])
    stage_label: str = Field(examples=["Analyzing pitch..."])
    progress: int = Field(ge=0, le=100, examples=[64])
    # Position in STAGE_ORDER so the app can tick off its steps.
    step_index: int = Field(ge=0)
    total_steps: int = Field(ge=1)
    is_simulated: bool
    completed_at: datetime | None = None
    error: AnalysisErrorInfo | None = None

    @classmethod
    def from_analysis(cls, analysis) -> "AnalysisStatusResponse":
        """Builds the response from an Analysis row."""
        stage = analysis.stage or "QUEUED"
        index = STAGE_ORDER.index(stage) if stage in STAGE_ORDER else 0
        error = None
        if analysis.status == "FAILED":
            error = AnalysisErrorInfo(
                code=analysis.error_code or "ANALYSIS_FAILED",
                message=analysis.error_message or "We could not finish analysing this performance.",
                credit_refunded=bool(analysis.credit_refunded),
            )
        return cls(
            analysis_id=analysis.id,
            status=analysis.status,
            stage=stage,
            stage_label=stage_label(stage),
            progress=int(analysis.progress or 0),
            step_index=index,
            total_steps=len(STAGE_ORDER),
            is_simulated=bool(analysis.is_simulated),
            completed_at=analysis.completed_at,
            error=error,
        )


# ==========================================================
# Lists and detail
# ==========================================================
class AnalysisSummary(APIModel):
    """One row in the user's list of analyses. Light: no metrics or curves."""

    id: uuid.UUID
    song_id: uuid.UUID
    song_title: str | None = None
    song_artist: str | None = None
    recording_id: uuid.UUID
    attempt_number: int

    status: str = Field(examples=["COMPLETED"])
    stage: str
    progress: int
    overall_score: float | None = Field(default=None, description="Null until completed.")
    status_label: str | None = None

    is_simulated: bool
    analysis_version: str
    created_at: datetime
    completed_at: datetime | None = None
