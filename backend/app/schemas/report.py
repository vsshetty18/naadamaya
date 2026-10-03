"""
NAADAMAYA report schemas: the finished comparison report.

Route:
    GET /reports/{analysis_id}  -> ReportResponse

This is the contract between the backend and the frontend Report page. The
frontend does not need to know how anything was calculated: it renders what
is here and draws a card only when its block is present.

Honesty rules built into the shape:
  - `metrics` contains ONLY metrics that were actually measured. A metric that
    could not be measured reliably is listed in `unavailable_metrics` with a
    reason. It never appears with a made-up score.
  - Optional blocks (pitch_comparison, sections, rhythm_comparison,
    pronunciation_analysis, breath_analysis) are null or empty when the engine
    did not return them. The frontend then shows no card for them.
  - `is_simulated` is true for every ANALYSIS_MODE=mock result, so a demo is
    never mistaken for real analysis.
  - Every insight carries the `evidence` (measured numbers and time range)
    that produced it.

Field names are snake_case. The frontend report adapter converts them to the
shapes its components already use (sectionName, startTime, ...), so no
component changes.

Responses never contain storage keys or paths. `audio_url` is a short-lived
signed link or an authenticated API path.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import APIModel


# ==========================================================
# Audio and song details
# ==========================================================
class ReportSong(APIModel):
    id: uuid.UUID
    title: str
    artist: str | None = None
    language: str | None = None
    duration: float | None = Field(default=None, description="Seconds.")
    tempo: float | None = Field(default=None, description="BPM measured from the audio. Null if unreliable.")
    key: str | None = Field(default=None, description="Estimated tonic, e.g. F#. Null if unreliable.")
    audio_url: str | None = None
    waveform: list[float] = Field(default_factory=list, description="Bars 0..1 from the real audio.")


class ReportRecording(APIModel):
    id: uuid.UUID
    recorded_at: datetime
    duration: float | None = None
    tempo: float | None = None
    audio_url: str | None = None
    waveform: list[float] = Field(default_factory=list)


class SongProfile(APIModel):
    """What kind of song this is, so the reader sees why these metrics were chosen."""

    summary: str | None = None
    tags: list[str] = Field(default_factory=list, examples=[["Slow tempo", "Long phrases"]])


# ==========================================================
# Metrics
# ==========================================================
class ReportMetric(APIModel):
    id: str = Field(examples=["pitch_accuracy"], description="Stable id the frontend maps to an icon.")
    name: str = Field(examples=["Pitch Accuracy"])
    score: float = Field(ge=0, le=100)
    status: str = Field(examples=["good"])
    relevance: str = Field(default="medium", examples=["high"])
    weight: float | None = Field(default=None, description="Configured weight.")
    effective_weight: float | None = Field(
        default=None, description="Weight after re-normalising over the metrics that were available."
    )
    description: str | None = None


class UnavailableMetric(APIModel):
    id: str
    name: str
    reason: str = Field(examples=["Pronunciation analysis unavailable for this recording."])


# ==========================================================
# Comparison and pitch
# ==========================================================
class SnapshotRow(APIModel):
    id: str = Field(examples=["tempo"])
    label: str = Field(examples=["Tempo (BPM)"])
    format: str = Field(default="text", description="text | number | time | cents | score | ms")
    original: Any | None = None
    user: Any | None = None
    difference: float | None = None


class ComparisonBlock(APIModel):
    reference_key: str | None = None
    user_key: str | None = None
    reference_tempo: float | None = None
    user_tempo: float | None = None
    snapshot: list[SnapshotRow] = Field(default_factory=list)


class PitchSample(APIModel):
    time: float = Field(description="Seconds.")
    pitch: float = Field(description="Hz.")


class PitchPoint(APIModel):
    """One aligned moment on the pitch graph."""

    t: float = Field(description="Seconds on the reference clock.")
    ref_hz: float | None = None
    user_hz: float | None = None
    ref_midi: float | None = None
    user_midi: float | None = None
    deviation_cents: float | None = Field(
        default=None, description="Positive = singer sharp, negative = flat."
    )
    confidence: float | None = Field(default=None, ge=0, le=1)


class PitchAnnotation(APIModel):
    start_time: float
    end_time: float
    type: str = Field(examples=["sharp"], description="sharp | flat | unstable")
    cents: int | None = None
    label: str | None = None


class PitchStats(APIModel):
    matched_percent: float | None = None
    sharp_percent: float | None = None
    flat_percent: float | None = None


class PitchAxisNote(APIModel):
    label: str = Field(examples=["Sa"])
    value: float = Field(description="Semitones above the detected tonic.")


class PitchComparisonBlock(APIModel):
    reference: list[PitchSample] = Field(default_factory=list)
    user: list[PitchSample] = Field(default_factory=list)
    points: list[PitchPoint] = Field(default_factory=list)
    annotations: list[PitchAnnotation] = Field(default_factory=list)
    stats: PitchStats | None = None
    mean_deviation_cents: float | None = None
    axis: list[PitchAxisNote] = Field(default_factory=list)
    notes: list[str] = Field(
        default_factory=list,
        description='Plain statements about reliability, e.g. "Pitch tracking was less certain in quiet parts".',
    )


# ==========================================================
# Sections, insights, recommendations
# ==========================================================
class SectionIssue(APIModel):
    type: str = Field(examples=["pitch"])
    label: str = Field(examples=["Pitch deviation"])


class ReportSection(APIModel):
    id: str = Field(examples=["chorus"])
    name: str = Field(examples=["Chorus"])
    start_time: float
    end_time: float
    score: float | None = None
    pitch_score: float | None = None
    timing_score: float | None = None
    stability_score: float | None = None
    status: str = Field(default="good", description="good | warning | critical")
    issues: list[SectionIssue] = Field(default_factory=list)
    note: str | None = None
    is_estimated: bool = Field(
        default=False, description="True when sections are an even split because no structure was detected."
    )


class ReportInsight(APIModel):
    type: str = Field(examples=["improvement"], description="positive | improvement | note")
    title: str
    description: str | None = None
    priority: int = 0
    evidence: dict[str, Any] = Field(
        default_factory=dict, description="The measurements behind this insight."
    )


class ReportRecommendation(APIModel):
    id: str
    title: str
    description: str | None = None
    priority: int = Field(ge=1, description="1 = most important.")
    metric_id: str | None = None
    section_id: str | None = None
    duration_minutes: int | None = None


class PerformanceNote(APIModel):
    """One line of the 'How You Performed' card."""

    type: str = Field(examples=["positive"], description="positive | improvement | issue")
    text: str


# ==========================================================
# Attempts
# ==========================================================
class AttemptPoint(APIModel):
    attempt: int
    score: float | None = None
    date: datetime
    analysis_id: uuid.UUID


class PreviousAttempt(APIModel):
    attempt_number: int
    analysis_id: uuid.UUID
    score: float | None = None
    delta: float | None = Field(default=None, description="This score minus the previous one.")
    metric_deltas: dict[str, float] = Field(
        default_factory=dict, description="Change per metric id where both attempts measured it."
    )


# ==========================================================
# The report
# ==========================================================
class ReportResponse(APIModel):
    analysis_id: uuid.UUID
    status: str = Field(examples=["COMPLETED"])
    attempt_number: int
    analysis_version: str
    analysis_mode: str = Field(examples=["real"], description="real | mock")
    is_simulated: bool
    created_at: datetime
    completed_at: datetime | None = None

    song: ReportSong
    recording: ReportRecording
    song_profile: SongProfile | None = None

    overall_score: float | None = Field(default=None, ge=0, le=100)
    status_label: str | None = Field(
        default=None, description="Wording for the score. The frontend derives one if null."
    )
    summary: str | None = None

    metrics: list[ReportMetric] = Field(default_factory=list)
    unavailable_metrics: list[UnavailableMetric] = Field(default_factory=list)

    comparison: ComparisonBlock | None = None
    pitch_comparison: PitchComparisonBlock | None = None
    sections: list[ReportSection] = Field(default_factory=list)

    # Optional blocks. Null when the engine could not produce them.
    # Shapes match the frontend components: {unit, entries}, {items}, {phrases}.
    rhythm_comparison: dict[str, Any] | None = None
    pronunciation_analysis: dict[str, Any] | None = None
    breath_analysis: dict[str, Any] | None = None

    performance: list[PerformanceNote] = Field(default_factory=list)
    insights: list[ReportInsight] = Field(default_factory=list)
    recommendations: list[ReportRecommendation] = Field(default_factory=list)

    previous_attempt: PreviousAttempt | None = None
    attempt_history: list[AttemptPoint] = Field(default_factory=list)
