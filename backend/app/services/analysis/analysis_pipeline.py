"""
NAADAMAYA analysis pipeline.

Called by the Celery worker (workers/analysis_worker.py, written later):

    result = run_pipeline(db, analysis)       # does the work, reports progress
    save_result(db, analysis, result)         # writes everything, marks COMPLETED

The worker owns status PROCESSING, failures and credit refunds. This module
owns the analysis itself.

Real mode (ANALYSIS_MODE=real), in order:
  load both processed WAVs -> pitch tracks -> alignment -> pitch, melody,
  rhythm, expression, stability, breath, pronunciation analyzers -> comparison
  -> sections -> scoring -> feedback

Mock mode (ANALYSIS_MODE=mock): mock_analysis.build_mock() only. Nothing is
measured, and the result is saved with is_simulated=True. The real analyzers
are not touched.

An analyzer that crashes does not fail the analysis: that metric becomes
"unavailable" and the others still count. If the audio itself is unusable the
pipeline raises InvalidAudioError and the worker fails the analysis (and
refunds the credit).

Both modes return the same dict shape (see mock_analysis.build_mock), so
save_result is identical for both.
"""

import math
import time
from typing import Any

import numpy as np
import soundfile as sf
from sqlalchemy.orm import Session

from app.analyzers.alignment_engine import align
from app.analyzers.breath_analyzer import SignalBreathAnalyzer
from app.analyzers.comparison_engine import compare
from app.analyzers.expression_analyzer import SignalExpressionAnalyzer
from app.analyzers.feedback_engine import RuleBasedFeedback
from app.analyzers.interfaces import (
    BREATH_CONTROL,
    MELODY_MATCHING,
    PITCH_ACCURACY,
    RHYTHM,
    STABILITY,
    AnalysisInputs,
    Analyzer,
    AnalyzerOutput,
    AudioFeatures,
    MetricResult,
)
from app.analyzers.melody_analyzer import SignalMelodyAnalyzer
from app.analyzers.pitch_analyzer import SignalPitchAnalyzer
from app.analyzers.pitch_extractor import get_pitch_extractor
from app.analyzers.pronunciation_analyzer import SignalPronunciationAnalyzer
from app.analyzers.rhythm_analyzer import SignalRhythmAnalyzer
from app.analyzers.scoring_engine import score as score_metrics
from app.analyzers.section_segmenter import build_sections
from app.analyzers.stability_analyzer import SignalStabilityAnalyzer
from app.core.config import settings
from app.core.exceptions import InvalidAudioError
from app.core.logging import get_logger, log_event
from app.core.security import utcnow
from app.models.analysis import (
    Analysis,
    AnalysisMetric,
    AnalysisSection,
    AnalysisTimeline,
    Insight,
    Recommendation,
)
from app.models.enums import AnalysisStage, AnalysisStatus
from app.models.recording import Recording
from app.models.song import Song
from app.services.audio.preprocessing import find_active_regions
from app.services.storage.storage_service import get_storage
from app.utils.audio_utils import waveform_peaks

log = get_logger("naadamaya.analysis.pipeline")

HIGH_ONSET_RATE = 2.5


# ==========================================================
# Progress (committed so the status endpoint can see it)
# ==========================================================
def set_progress(db: Session, analysis: Analysis, stage: AnalysisStage, percent: int) -> None:
    analysis.stage = stage.value
    analysis.progress = max(0, min(100, int(percent)))
    db.commit()


# ==========================================================
# JSON safety (numpy values and NaN must never reach the database)
# ==========================================================
def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return _safe(value.tolist())
    if isinstance(value, np.generic):
        return _safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


# ==========================================================
# Real analysis
# ==========================================================
def _load_features(key: str, warnings: list[str]) -> AudioFeatures:
    storage = get_storage()
    with storage.materialize(key) as path:
        try:
            samples, sample_rate = sf.read(path, dtype="float32", always_2d=False)
        except (RuntimeError, sf.LibsndfileError) as exc:
            raise InvalidAudioError("This audio file could not be read.") from exc

    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    if samples.size == 0:
        raise InvalidAudioError("This audio file is empty.")

    regions, _ = find_active_regions(samples, sample_rate)
    if not regions:
        raise InvalidAudioError("We could not hear any sound in this recording.")

    return AudioFeatures(
        samples=samples,
        sample_rate=int(sample_rate),
        duration=float(samples.size) / float(sample_rate),
        active_regions=regions,
        leading_silence=float(regions[0][0]),
        warnings=list(warnings),
    )


def _run_one(analyzer: Analyzer, inputs: AnalysisInputs) -> AnalyzerOutput:
    """A crashing analyzer becomes an unavailable metric. It never fails the analysis."""
    try:
        return analyzer.analyze(inputs)
    except Exception:  # noqa: BLE001
        log.exception("analyzer %s failed", analyzer.metric_id)
        return AnalyzerOutput(MetricResult.unavailable(analyzer.metric_id))


def _song_profile(outputs: dict[str, AnalyzerOutput]) -> dict[str, Any] | None:
    """Tags come only from measured facts."""
    tags: list[str] = []
    rhythm = outputs.get(RHYTHM)
    if rhythm and rhythm.metric.available and (rhythm.details.get("onset_rate") or 0) >= HIGH_ONSET_RATE:
        tags.append("Rhythmic")
    melody = outputs.get(MELODY_MATCHING)
    if melody and melody.metric.available and melody.metric.relevance == "high":
        tags.append("Melodic")
    stability = outputs.get(STABILITY)
    if stability and stability.metric.available and stability.metric.relevance == "high":
        tags.append("Held notes")
    breath = outputs.get(BREATH_CONTROL)
    if breath and breath.metric.available and breath.metric.relevance == "high":
        tags.append("Long phrases")
    return {"summary": None, "tags": tags} if tags else None


def _section_for(sections, start: float | None) -> str | None:
    if start is None:
        return None
    for s in sections:
        if s.start <= start < s.end:
            return s.key
    return None


def _run_real(db: Session, analysis: Analysis, song: Song, recording: Recording) -> dict[str, Any]:
    if not song.processed_file_key or not recording.processed_file_key:
        raise InvalidAudioError("The audio for this analysis is missing.")

    set_progress(db, analysis, AnalysisStage.PREPROCESSING, 8)
    reference = _load_features(song.processed_file_key, (song.metadata_ or {}).get("warnings", []))
    user = _load_features(recording.processed_file_key, (recording.metadata_ or {}).get("warnings", []))

    # Pitch tracking is the slowest step.
    set_progress(db, analysis, AnalysisStage.PREPROCESSING, 15)
    extractor = get_pitch_extractor()
    reference.pitch = extractor.extract(reference.samples, reference.sample_rate)
    set_progress(db, analysis, AnalysisStage.PREPROCESSING, 28)
    user.pitch = extractor.extract(user.samples, user.sample_rate)

    set_progress(db, analysis, AnalysisStage.ALIGNMENT, 40)
    inputs = AnalysisInputs(
        reference=reference,
        user=user,
        language=song.language,
        lyrics=song.lyrics,
    )
    inputs.alignment = align(reference, user)

    outputs: dict[str, AnalyzerOutput] = {}

    set_progress(db, analysis, AnalysisStage.PITCH_ANALYSIS, 52)
    for analyzer in (SignalPitchAnalyzer(), SignalMelodyAnalyzer()):
        outputs[analyzer.metric_id] = _run_one(analyzer, inputs)

    set_progress(db, analysis, AnalysisStage.RHYTHM_ANALYSIS, 64)
    for analyzer in (SignalRhythmAnalyzer(), SignalExpressionAnalyzer()):
        outputs[analyzer.metric_id] = _run_one(analyzer, inputs)

    set_progress(db, analysis, AnalysisStage.STABILITY_ANALYSIS, 76)
    for analyzer in (SignalStabilityAnalyzer(), SignalBreathAnalyzer(), SignalPronunciationAnalyzer()):
        outputs[analyzer.metric_id] = _run_one(analyzer, inputs)

    set_progress(db, analysis, AnalysisStage.SCORING, 86)
    ordered = list(outputs.values())
    comparison = compare(inputs, ordered)
    sections = build_sections(reference, ordered, inputs.alignment)

    metric_results = [o.metric for o in ordered]
    scored = score_metrics(metric_results)
    findings = [f for o in ordered for f in o.findings]

    set_progress(db, analysis, AnalysisStage.REPORT_GENERATION, 94)
    feedback = RuleBasedFeedback().generate(
        metric_results, findings, {"sections": sections, "language": song.language}
    )
    recommendations = []
    for r in feedback["recommendations"]:
        r = dict(r)
        r["section_key"] = _section_for(sections, r.pop("start", None))
        recommendations.append(r)

    pitch = outputs.get(PITCH_ACCURACY)
    pitch_details = pitch.details if pitch and pitch.metric.available else {}
    rhythm = outputs.get(RHYTHM)
    breath = outputs.get(BREATH_CONTROL)

    measured_count = sum(1 for m in metric_results if m.available)
    if scored.overall is None:
        summary = scored.reason
    else:
        summary = f"Based on {measured_count} measured area(s) of your performance."
        missing = len(metric_results) - measured_count
        if missing:
            summary += f" {missing} area(s) could not be measured reliably."

    extras: dict[str, Any] = {
        "comparison": {
            "reference_key": comparison.reference_key,
            "user_key": comparison.user_key,
            "reference_tempo": comparison.reference_tempo,
            "user_tempo": comparison.user_tempo,
        },
        "pitch_notes": pitch_details.get("notes", []),
        "mean_deviation_cents": pitch_details.get("mean_deviation_cents"),
    }
    profile = _song_profile(outputs)
    if profile:
        extras["song_profile"] = profile
    if rhythm and rhythm.metric.available:
        extras["rhythm_comparison"] = rhythm.details.get("rhythm_comparison")
    if breath and breath.metric.available:
        extras["breath_analysis"] = breath.details.get("breath_analysis")

    return {
        "overall_score": scored.overall,
        "summary": summary,
        "metrics": [
            {
                "metric_id": m.metric_id,
                "name": m.name,
                "available": m.available,
                "score": m.score,
                "status": m.status,
                "relevance": m.relevance,
                "weight": m.weight,
                "effective_weight": m.effective_weight,
                "description": m.description,
                "unavailable_reason": m.unavailable_reason,
            }
            for m in metric_results
        ],
        "sections": [s.to_model_fields() for s in sections],
        "pitch_points": pitch_details.get("pitch_points", []),
        "annotations": pitch_details.get("annotations", []),
        "pitch_stats": pitch_details.get("stats"),
        "snapshot": comparison.rows,
        "insights": feedback["insights"],
        "performance": feedback["performance"],
        "recommendations": recommendations,
        "reference_waveform": waveform_peaks(reference.samples),
        "user_waveform": waveform_peaks(user.samples),
        "extras": extras,
    }


# ==========================================================
# Mock analysis (development only)
# ==========================================================
def _run_mock(db: Session, analysis: Analysis, song: Song) -> dict[str, Any]:
    from app.services.analysis.mock_analysis import build_mock

    for stage, pct in (
        (AnalysisStage.PREPROCESSING, 15),
        (AnalysisStage.ALIGNMENT, 35),
        (AnalysisStage.PITCH_ANALYSIS, 55),
        (AnalysisStage.RHYTHM_ANALYSIS, 70),
        (AnalysisStage.STABILITY_ANALYSIS, 80),
        (AnalysisStage.SCORING, 90),
        (AnalysisStage.REPORT_GENERATION, 95),
    ):
        set_progress(db, analysis, stage, pct)
        time.sleep(0.6)  # so the progress screen is visible while developing the app
    return build_mock(song.id, analysis.attempt_number, song.duration or 180.0)


# ==========================================================
# Public entry points
# ==========================================================
def run_pipeline(db: Session, analysis: Analysis) -> dict[str, Any]:
    song = db.get(Song, analysis.song_id)
    recording = db.get(Recording, analysis.recording_id)
    if song is None or recording is None or song.is_deleted or recording.is_deleted:
        raise InvalidAudioError("The audio for this analysis is no longer available.")

    log_event(log, "analysis_pipeline_started", analysis_id=str(analysis.id), mode=settings.analysis_mode)
    if settings.use_mock_analysis:
        return _run_mock(db, analysis, song)
    return _run_real(db, analysis, song, recording)


def save_result(db: Session, analysis: Analysis, result: dict[str, Any]) -> None:
    """Writes the result and marks the analysis COMPLETED. Safe to call again on a retry."""
    result = _safe(result)

    analysis.metrics.clear()
    analysis.sections.clear()
    analysis.insights.clear()
    analysis.recommendations.clear()
    analysis.timeline = None
    db.flush()

    for i, m in enumerate(result["metrics"]):
        analysis.metrics.append(
            AnalysisMetric(
                metric_type=m["metric_id"],
                name=m["name"],
                available=m["available"],
                score=m.get("score"),
                status=m["status"],
                weight=m.get("weight"),
                effective_weight=m.get("effective_weight"),
                relevance=m.get("relevance", "medium"),
                description=m.get("description"),
                unavailable_reason=m.get("unavailable_reason"),
                position=i,
            )
        )
    for s in result["sections"]:
        analysis.sections.append(AnalysisSection(**s))
    for ins in result["insights"]:
        analysis.insights.append(
            Insight(
                type=ins["type"],
                title=ins["title"][:200],
                description=ins.get("description"),
                priority=ins.get("priority", 0),
                evidence=ins.get("evidence") or {},
            )
        )
    for r in result["recommendations"]:
        analysis.recommendations.append(
            Recommendation(
                title=r["title"][:200],
                description=r.get("description"),
                priority=r["priority"],
                metric_type=r.get("metric_type"),
                section_key=r.get("section_key"),
                duration_minutes=r.get("duration_minutes"),
            )
        )
    analysis.timeline = AnalysisTimeline(
        pitch_points=result["pitch_points"],
        annotations=result["annotations"],
        reference_waveform=result["reference_waveform"],
        user_waveform=result["user_waveform"],
    )

    extras = dict(result.get("extras") or {})
    extras["snapshot"] = result.get("snapshot") or []
    extras["pitch_stats"] = result.get("pitch_stats")
    extras["performance"] = result.get("performance") or []

    simulated = settings.use_mock_analysis
    analysis.overall_score = result.get("overall_score")
    analysis.summary = result.get("summary")
    analysis.report_extras = extras
    analysis.analysis_mode = "mock" if simulated else "real"
    analysis.is_simulated = simulated
    analysis.analysis_version = settings.analysis_version
    analysis.status = AnalysisStatus.COMPLETED.value
    analysis.stage = AnalysisStage.COMPLETED.value
    analysis.progress = 100
    analysis.completed_at = utcnow()
    analysis.error_code = None
    analysis.error_message = None
    db.flush()

    log_event(
        log,
        "analysis_completed",
        analysis_id=str(analysis.id),
        score=analysis.overall_score,
        simulated=simulated,
    )
