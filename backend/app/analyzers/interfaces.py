"""
NAADAMAYA analyzer interfaces.

Every part of the analysis is a small, replaceable module behind one of the
interfaces below. Today they are signal-processing implementations. Later a
trained model (CREPE for pitch, a Carnatic raga model for melody, a speech
recogniser for pronunciation) can replace any one of them without touching
the rest of the pipeline.

Shared rules for every analyzer:
  - Input is AnalysisInputs: the reference and the singer's audio, already
    preprocessed (services/audio/preprocessing.py).
  - Output is AnalyzerOutput: ONE MetricResult plus the specific Findings that
    explain it (what happened, where, how big).
  - If a metric cannot be measured reliably the analyzer returns
    MetricResult.unavailable(...) with a reason. It NEVER returns a made-up
    score. The scoring engine leaves unavailable metrics out and re-normalises
    the weights of the rest.
  - Findings carry the measured numbers (cents, seconds, ratios). The
    feedback engine writes sentences ONLY from findings, so every piece of
    feedback traces back to something detected in the audio.
  - "Insufficient data" is a valid and honest answer.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np


# ==========================================================
# Metric ids and names (the ids the frontend maps to icons/colours)
# ==========================================================
PITCH_ACCURACY = "pitch_accuracy"
MELODY_MATCHING = "melody_matching"
RHYTHM = "rhythm"
STABILITY = "stability"
EXPRESSION = "expression"
PRONUNCIATION = "pronunciation"
BREATH_CONTROL = "breath_control"

METRIC_NAMES: dict[str, str] = {
    PITCH_ACCURACY: "Pitch Accuracy",
    MELODY_MATCHING: "Melody Matching",
    RHYTHM: "Rhythm & Timing",
    STABILITY: "Stability",
    EXPRESSION: "Expression & Dynamics",   # measured loudness/energy similarity, NOT emotion
    PRONUNCIATION: "Pronunciation",
    BREATH_CONTROL: "Breath Consistency",  # audio-based indicators only, no medical claims
}

# Wording used when a metric could not be measured.
REASON_INSUFFICIENT = "Insufficient data for reliable analysis."
REASON_PRONUNCIATION = "Pronunciation analysis unavailable for this recording."
REASON_BREATH = "Insufficient audio data for reliable breath analysis."


def score_to_status(score: float) -> str:
    """Same bands as the frontend, so a metric reads the same everywhere."""
    if score >= 90:
        return "excellent"
    if score >= 80:
        return "very_good"
    if score >= 70:
        return "good"
    if score >= 55:
        return "needs_practice"
    return "needs_improvement"


# ==========================================================
# Pitch data
# ==========================================================
@dataclass
class PitchTrack:
    """
    The pitch of one recording over time.

    times       seconds, one per frame (evenly spaced)
    hz          fundamental frequency; NaN where nothing reliable was heard
                (never 0, so a gap cannot be mistaken for a low note)
    confidence  0..1 per frame, how sure the tracker was
    """

    times: np.ndarray
    hz: np.ndarray
    confidence: np.ndarray
    method: str = "unknown"    # which extractor made it, e.g. "pyin"

    def __post_init__(self) -> None:
        self.times = np.asarray(self.times, dtype=float)
        self.hz = np.asarray(self.hz, dtype=float)
        self.confidence = np.asarray(self.confidence, dtype=float)
        if not (self.times.shape == self.hz.shape == self.confidence.shape):
            raise ValueError("PitchTrack arrays must have the same length.")

    @property
    def voiced(self) -> np.ndarray:
        return np.isfinite(self.hz)

    @property
    def voiced_ratio(self) -> float:
        return float(self.voiced.mean()) if self.hz.size else 0.0

    @property
    def hop_seconds(self) -> float:
        return float(self.times[1] - self.times[0]) if self.times.size > 1 else 0.0

    def __len__(self) -> int:
        return int(self.times.size)


@dataclass
class AlignedPitch:
    """
    The two pitch tracks matched moment-to-moment on the REFERENCE clock
    (the alignment engine produces this; every pitch-based analyzer consumes it).

    deviation_cents is positive when the singer is sharp, negative when flat,
    NaN where either side had no reliable pitch.
    """

    times: np.ndarray            # reference-clock seconds
    ref_hz: np.ndarray
    user_hz: np.ndarray
    deviation_cents: np.ndarray
    confidence: np.ndarray       # the lower of the two tracks' confidences
    user_times: np.ndarray       # where each moment was in the singer's recording

    @property
    def comparable(self) -> np.ndarray:
        """Frames where both sides had a reliable pitch."""
        return np.isfinite(self.deviation_cents)


@dataclass
class AlignmentResult:
    """How the singer's performance lines up with the reference in time."""

    aligned_pitch: AlignedPitch | None
    start_offset: float = 0.0        # singer began this many seconds after the reference (can be negative)
    tempo_ratio: float | None = None  # singer duration / reference duration over the sung part
    # Matched (reference_seconds, user_seconds) points along the alignment path.
    path: list[tuple[float, float]] = field(default_factory=list)
    quality: float = 0.0             # 0..1, how trustworthy the alignment is
    notes: list[str] = field(default_factory=list)


# ==========================================================
# Audio inputs
# ==========================================================
@dataclass
class AudioFeatures:
    """One recording after preprocessing, plus anything extracted from it."""

    samples: np.ndarray
    sample_rate: int
    duration: float
    active_regions: list[tuple[float, float]]   # seconds, from signal energy
    leading_silence: float = 0.0
    pitch: PitchTrack | None = None             # filled in by the pitch extractor
    warnings: list[str] = field(default_factory=list)  # e.g. "clipping", "very_quiet"


@dataclass
class AnalysisInputs:
    reference: AudioFeatures
    user: AudioFeatures
    alignment: AlignmentResult | None = None   # filled in by the alignment engine
    language: str | None = None
    lyrics: str | None = None                  # reference lyrics, if the singer supplied them


# ==========================================================
# Results
# ==========================================================
@dataclass
class Finding:
    """
    One detected fact: what, where, and how much. The feedback engine builds
    its sentences from these and nothing else.

    kind        a stable code, e.g. "pitch_sharp", "pitch_flat", "late_entry",
                "tempo_drift", "unstable_note", "breath_short", "energy_flat"
    severity    0..1 (how much it hurts the performance)
    evidence    the measured numbers, e.g. {"cents": 31, "ratio": 0.74}
    """

    kind: str
    metric_id: str
    start: float                    # seconds on the reference clock
    end: float
    severity: float
    evidence: dict[str, Any] = field(default_factory=dict)
    label: str | None = None        # short tag for the timeline, e.g. "Pitch deviation"


@dataclass
class MetricResult:
    metric_id: str
    name: str
    available: bool
    score: float | None = None      # 0..100, None when unavailable
    status: str = "unavailable"
    relevance: str = "medium"       # high | medium | low (how much this song depends on it)
    description: str | None = None
    unavailable_reason: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def measured(
        cls,
        metric_id: str,
        score: float,
        description: str | None = None,
        *,
        relevance: str = "medium",
        evidence: dict[str, Any] | None = None,
    ) -> "MetricResult":
        score = float(max(0.0, min(100.0, score)))
        return cls(
            metric_id=metric_id,
            name=METRIC_NAMES.get(metric_id, metric_id.replace("_", " ").title()),
            available=True,
            score=round(score, 1),
            status=score_to_status(score),
            relevance=relevance,
            description=description,
            evidence=evidence or {},
        )

    @classmethod
    def unavailable(
        cls,
        metric_id: str,
        reason: str = REASON_INSUFFICIENT,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> "MetricResult":
        return cls(
            metric_id=metric_id,
            name=METRIC_NAMES.get(metric_id, metric_id.replace("_", " ").title()),
            available=False,
            score=None,
            status="unavailable",
            unavailable_reason=reason,
            evidence=evidence or {},
        )


@dataclass
class AnalyzerOutput:
    metric: MetricResult
    findings: list[Finding] = field(default_factory=list)
    # Extra data other modules or the report may use (per-section scores, curves, ...).
    details: dict[str, Any] = field(default_factory=dict)


# ==========================================================
# The interfaces
# ==========================================================
class PitchExtractor(ABC):
    """Turns audio into a PitchTrack. Replaceable: pYIN today, CREPE later."""

    name: str = "base"

    @abstractmethod
    def extract(self, samples: np.ndarray, sample_rate: int) -> PitchTrack: ...


class Analyzer(ABC):
    """Base for every metric analyzer."""

    metric_id: str = ""

    @abstractmethod
    def analyze(self, inputs: AnalysisInputs) -> AnalyzerOutput:
        """Must not raise for 'not enough data'. Return MetricResult.unavailable instead."""


class PitchAnalyzer(Analyzer):
    """Pitch accuracy of the singer against the reference."""

    metric_id = PITCH_ACCURACY


class MelodyAnalyzer(Analyzer):
    """
    Melody / note-sequence match. The MVP compares pitch movement, not raga
    grammar. Future: CarnaticMelodyAnalyzer, HindustaniMelodyAnalyzer,
    WesternMelodyAnalyzer implement this same interface.
    """

    metric_id = MELODY_MATCHING


class RhythmAnalyzer(Analyzer):
    """Timing, tempo and entries."""

    metric_id = RHYTHM


class StabilityAnalyzer(Analyzer):
    """Steadiness of held notes and pitch fluctuation."""

    metric_id = STABILITY


class ExpressionAnalyzer(Analyzer):
    """Similarity of loudness/energy contour. Measured, not 'emotion'."""

    metric_id = EXPRESSION


class PronunciationAnalyzer(Analyzer):
    """Lyric/diction match. Unavailable unless recognition is reliable."""

    metric_id = PRONUNCIATION


class BreathAnalyzer(Analyzer):
    """Phrase length, breaks and amplitude drops as breath indicators."""

    metric_id = BREATH_CONTROL


class FeedbackGenerator(ABC):
    """
    Turns findings into user-facing insights and recommendations. Rule-based
    today; an AI teacher can implement this later.
    """

    @abstractmethod
    def generate(
        self,
        metrics: list[MetricResult],
        findings: list[Finding],
        context: dict[str, Any],
    ) -> dict[str, Any]: ...


class VoiceAnalyzer(ABC):
    """
    RESERVED for future features (voice profile, vocal range measurement, song
    recommendation). Nothing implements this yet, and nothing pretends to.
    """

    @abstractmethod
    def profile(self, features: AudioFeatures) -> dict[str, Any]: ...
