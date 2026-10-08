"""
NAADAMAYA report generator.

    report = get_report(db, user_id, analysis_id)     # GET /reports/{analysis_id}

Reads a COMPLETED analysis from the database and builds the ReportResponse the
frontend renders. It measures and decides nothing: every value was saved by the
pipeline (or the mock) earlier. It only reshapes it.

Security: get_report() is the single place that checks ownership. An analysis
that belongs to someone else, is deleted, or does not exist all answer
"not found", so IDs cannot be probed.

Honesty rules carried through:
  - Metrics that could not be measured go to `unavailable_metrics` with their
    reason. They never appear in `metrics` with a score.
  - Optional blocks (pitch, sections, rhythm, pronunciation, breath) are left
    empty or null when the pipeline did not save them, so the frontend draws
    no card for them.
  - is_simulated and analysis_mode are passed through unchanged.

What the pipeline must save in Analysis.report_extras (all optional):
    song_profile            {summary, tags}
    comparison              {reference_key, user_key, reference_tempo, user_tempo}
    snapshot                [{id, label, format, original, user, difference}]
    pitch_stats             {matched_percent, sharp_percent, flat_percent}
    pitch_notes             [str]
    mean_deviation_cents    number
    rhythm_comparison       {unit, entries}
    pronunciation_analysis  {items}
    breath_analysis         {phrases}
    performance             [{type, text}]
"""

import math
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.models.analysis import Analysis
from app.models.enums import AnalysisStatus
from app.models.recording import Recording
from app.models.song import Song
from app.schemas.report import (
    AttemptPoint,
    ComparisonBlock,
    PerformanceNote,
    PitchAnnotation,
    PitchAxisNote,
    PitchComparisonBlock,
    PitchPoint,
    PitchSample,
    PitchStats,
    PreviousAttempt,
    ReportInsight,
    ReportMetric,
    ReportRecommendation,
    ReportRecording,
    ReportResponse,
    ReportSection,
    ReportSong,
    SectionIssue,
    SnapshotRow,
    SongProfile,
    UnavailableMetric,
)
from app.services.storage.storage_service import build_download_url
from app.utils.audio_utils import midi_to_note_name

NATURAL_NOTES = {0, 2, 4, 5, 7, 9, 11}
MAX_AXIS_LABELS = 6


# ==========================================================
# Small helpers
# ==========================================================
def _audio_url(key: str | None, local_path: str, filename: str | None) -> str | None:
    """
    A signed link when storage can make one (S3/R2). On local storage there is
    no safe public link, so an authenticated API path is returned instead; the
    app fetches it with its access token.
    """
    if not key:
        return None
    return build_download_url(key, filename) or f"{settings.api_v1_prefix}{local_path}"


def _axis(points: list[dict]) -> list[PitchAxisNote]:
    """
    Note labels for the pitch graph. `value` is the MIDI number and the label is
    the plain note name (C4, D4...). No Sa/Re/Ga is claimed: that would need the
    singer's tonic, which the MVP cannot reliably tell.
    """
    midis = [
        float(p[k]) for p in points for k in ("ref_midi", "user_midi")
        if p.get(k) is not None and math.isfinite(float(p[k]))
    ]
    if len(midis) < 2:
        return []
    naturals = [m for m in range(math.floor(min(midis)), math.ceil(max(midis)) + 1) if m % 12 in NATURAL_NOTES]
    if len(naturals) > MAX_AXIS_LABELS:
        naturals = naturals[:: math.ceil(len(naturals) / MAX_AXIS_LABELS)]
    return [PitchAxisNote(label=midi_to_note_name(m) or str(m), value=float(m)) for m in naturals]


def _pitch_block(timeline, extras: dict) -> PitchComparisonBlock | None:
    points = list(timeline.pitch_points or []) if timeline else []
    if len(points) < 2:
        return None

    reference = [PitchSample(time=p["t"], pitch=p["ref_hz"]) for p in points if p.get("ref_hz") is not None]
    user = [PitchSample(time=p["t"], pitch=p["user_hz"]) for p in points if p.get("user_hz") is not None]

    annotations = [
        PitchAnnotation(
            start_time=a["startTime"], end_time=a["endTime"], type=a["type"],
            cents=a.get("cents"), label=a.get("label"),
        )
        for a in (timeline.annotations or [])
    ]
    stats = extras.get("pitch_stats")
    return PitchComparisonBlock(
        reference=reference,
        user=user,
        points=[PitchPoint(**{k: p.get(k) for k in PitchPoint.model_fields}) for p in points],
        annotations=annotations,
        stats=PitchStats(**stats) if stats else None,
        mean_deviation_cents=extras.get("mean_deviation_cents"),
        axis=_axis(points),
        notes=list(extras.get("pitch_notes") or []),
    )


def _history(db: Session, user_id: uuid.UUID, song_id: uuid.UUID) -> list[Analysis]:
    return list(
        db.scalars(
            select(Analysis)
            .where(
                Analysis.user_id == user_id,
                Analysis.song_id == song_id,
                Analysis.status == AnalysisStatus.COMPLETED.value,
                Analysis.is_deleted.is_(False),
            )
            .order_by(Analysis.attempt_number)
        )
    )


def _previous(current: Analysis, history: list[Analysis]) -> PreviousAttempt | None:
    earlier = [a for a in history if a.attempt_number < current.attempt_number]
    if not earlier:
        return None
    prev = earlier[-1]

    delta = None
    if current.overall_score is not None and prev.overall_score is not None:
        delta = round(current.overall_score - prev.overall_score, 1)

    before = {m.metric_type: m.score for m in prev.metrics if m.available and m.score is not None}
    deltas = {
        m.metric_type: round(m.score - before[m.metric_type], 1)
        for m in current.metrics
        if m.available and m.score is not None and m.metric_type in before
    }
    return PreviousAttempt(
        attempt_number=prev.attempt_number,
        analysis_id=prev.id,
        score=prev.overall_score,
        delta=delta,
        metric_deltas=deltas,
    )


# ==========================================================
# The report
# ==========================================================
def build_report(db: Session, analysis: Analysis) -> ReportResponse:
    if analysis.status != AnalysisStatus.COMPLETED.value:
        raise ConflictError("This report is not ready yet.", code="REPORT_NOT_READY")

    song = db.get(Song, analysis.song_id)
    recording = db.get(Recording, analysis.recording_id)
    if song is None or recording is None:
        raise NotFoundError("We could not find this report.")

    extras: dict[str, Any] = analysis.report_extras or {}
    timeline = analysis.timeline
    comparison = extras.get("comparison") or {}
    snapshot = extras.get("snapshot") or []

    metrics = [
        ReportMetric(
            id=m.metric_type, name=m.name, score=m.score, status=m.status,
            relevance=m.relevance, weight=m.weight, effective_weight=m.effective_weight,
            description=m.description,
        )
        for m in analysis.metrics if m.available and m.score is not None
    ]
    unavailable = [
        UnavailableMetric(id=m.metric_type, name=m.name, reason=m.unavailable_reason or "Insufficient data for reliable analysis.")
        for m in analysis.metrics if not m.available
    ]

    sections = [
        ReportSection(
            id=s.section_key, name=s.section_name, start_time=s.start_time, end_time=s.end_time,
            score=s.score, pitch_score=s.pitch_score, timing_score=s.timing_score,
            stability_score=s.stability_score, status=s.status,
            issues=[SectionIssue(**i) for i in (s.issues or [])],
            note=s.note, is_estimated=s.is_estimated,
        )
        for s in analysis.sections
    ]

    history = _history(db, analysis.user_id, analysis.song_id)

    comparison_block = None
    if comparison or snapshot:
        comparison_block = ComparisonBlock(
            reference_key=comparison.get("reference_key"),
            user_key=comparison.get("user_key"),
            reference_tempo=comparison.get("reference_tempo"),
            user_tempo=comparison.get("user_tempo"),
            snapshot=[SnapshotRow(**{k: row.get(k) for k in SnapshotRow.model_fields}) for row in snapshot],
        )

    profile = extras.get("song_profile")

    return ReportResponse(
        analysis_id=analysis.id,
        status=analysis.status,
        attempt_number=analysis.attempt_number,
        analysis_version=analysis.analysis_version,
        analysis_mode=analysis.analysis_mode,
        is_simulated=analysis.is_simulated,
        created_at=analysis.created_at,
        completed_at=analysis.completed_at,
        song=ReportSong(
            id=song.id, title=song.title, artist=song.artist, language=song.language,
            duration=song.duration,
            tempo=comparison.get("reference_tempo"), key=comparison.get("reference_key"),
            audio_url=_audio_url(song.original_file_key, f"/songs/{song.id}/audio", song.original_filename),
            waveform=list(timeline.reference_waveform or []) if timeline else [],
        ),
        recording=ReportRecording(
            id=recording.id, recorded_at=recording.created_at, duration=recording.duration,
            tempo=comparison.get("user_tempo"),
            audio_url=_audio_url(recording.original_file_key, f"/recordings/{recording.id}/audio", recording.original_filename),
            waveform=list(timeline.user_waveform or []) if timeline else [],
        ),
        song_profile=SongProfile(summary=profile.get("summary"), tags=list(profile.get("tags") or [])) if profile else None,
        overall_score=analysis.overall_score,
        status_label=analysis.status_label,
        summary=analysis.summary,
        metrics=metrics,
        unavailable_metrics=unavailable,
        comparison=comparison_block,
        pitch_comparison=_pitch_block(timeline, extras),
        sections=sections,
        rhythm_comparison=extras.get("rhythm_comparison") or None,
        pronunciation_analysis=extras.get("pronunciation_analysis") or None,
        breath_analysis=extras.get("breath_analysis") or None,
        performance=[PerformanceNote(**p) for p in (extras.get("performance") or [])],
        insights=[
            ReportInsight(type=i.type, title=i.title, description=i.description, priority=i.priority, evidence=i.evidence or {})
            for i in analysis.insights
        ],
        recommendations=[
            ReportRecommendation(
                id=str(r.id), title=r.title, description=r.description, priority=r.priority,
                metric_id=r.metric_type, section_id=r.section_key, duration_minutes=r.duration_minutes,
            )
            for r in analysis.recommendations
        ],
        previous_attempt=_previous(analysis, history),
        attempt_history=[
            AttemptPoint(attempt=a.attempt_number, score=a.overall_score, date=a.completed_at or a.created_at, analysis_id=a.id)
            for a in history
        ],
    )


def get_report(db: Session, user_id: uuid.UUID, analysis_id: uuid.UUID) -> ReportResponse:
    """Ownership-checked entry point used by GET /reports/{analysis_id}."""
    analysis = db.get(Analysis, analysis_id)
    if analysis is None or analysis.user_id != user_id or analysis.is_deleted:
        raise NotFoundError("We could not find this report.")
    return build_report(db, analysis)
