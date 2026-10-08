"""
NAADAMAYA comparison engine.

    result = compare(inputs, outputs)

Builds the "Comparison Snapshot" (the table of Original vs Your Voice) and the
key/tempo facts from what was MEASURED. It does no scoring and invents
nothing: a row appears only when its value could be measured, and a value that
does not apply to one side is None (shown as a dash in the app).

Rows (each only when measurable):
  key              estimated tonic of each recording (Krumhansl-style key
                   profile on chroma). An estimate, and unreliable for
                   heavily ornamented or non-Western music, so it is only
                   reported when the winning key clearly beats the runner-up.
  tempo            BPM estimate from the rhythm analyzer, information only
  duration         length of each recording, in seconds
  vocal_range      lowest and highest reliable note of each recording
  pitch_deviation  singer's mean deviation from the original, in cents
  timing_offset    singer's median lag against the original, in ms
  stability_score  the stability metric's score (singer only)

Output "format" values match the frontend ComparisonSnapshot component:
text | number | time | cents | score | ms.

Also returned for the report:
  reference_key, user_key, reference_tempo, user_tempo
"""

from dataclasses import dataclass, field

import librosa
import numpy as np

from app.analyzers.interfaces import (
    PITCH_ACCURACY,
    RHYTHM,
    STABILITY,
    AnalysisInputs,
    AnalyzerOutput,
    AudioFeatures,
)
from app.utils.audio_utils import hz_to_midi, midi_to_note_name

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Kessler major/minor key profiles.
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

MIN_KEY_MARGIN = 0.05        # best key must beat the runner-up by this much
MIN_RANGE_FRAMES = 60
MIN_CONFIDENCE = 0.5


@dataclass
class ComparisonResult:
    rows: list[dict] = field(default_factory=list)
    reference_key: str | None = None
    user_key: str | None = None
    reference_tempo: float | None = None
    user_tempo: float | None = None


def estimate_key(features: AudioFeatures) -> str | None:
    """Tonic estimate like 'F#' or 'A minor'. None when the answer is not clear."""
    try:
        chroma = librosa.feature.chroma_cqt(y=features.samples, sr=features.sample_rate)
        profile = chroma.mean(axis=1)
        if not np.isfinite(profile).all() or profile.std() < 1e-6:
            return None
        scores = []
        for tonic in range(12):
            for mode, template in (("", MAJOR), ("m", MINOR)):
                corr = float(np.corrcoef(profile, np.roll(template, tonic))[0, 1])
                scores.append((corr, f"{NOTE_NAMES[tonic]}{mode}"))
        scores.sort(reverse=True)
        if scores[0][0] - scores[1][0] < MIN_KEY_MARGIN:
            return None
        return scores[0][1]
    except Exception:  # noqa: BLE001 - key is optional information
        return None


def vocal_range(features: AudioFeatures) -> tuple[str, str] | None:
    """Lowest and highest reliable note (5th and 95th percentile, so stray frames do not count)."""
    track = features.pitch
    if track is None:
        return None
    ok = np.isfinite(track.hz) & (track.confidence >= MIN_CONFIDENCE)
    if int(ok.sum()) < MIN_RANGE_FRAMES:
        return None
    midi = np.asarray(hz_to_midi(track.hz[ok]), dtype=float)
    low = midi_to_note_name(float(np.percentile(midi, 5)))
    high = midi_to_note_name(float(np.percentile(midi, 95)))
    return (low, high) if low and high else None


def _by_metric(outputs: list[AnalyzerOutput], metric_id: str) -> AnalyzerOutput | None:
    return next((o for o in outputs if o.metric.metric_id == metric_id), None)


def compare(inputs: AnalysisInputs, outputs: list[AnalyzerOutput]) -> ComparisonResult:
    ref, user = inputs.reference, inputs.user
    result = ComparisonResult()

    result.reference_key = estimate_key(ref)
    result.user_key = estimate_key(user)

    rhythm = _by_metric(outputs, RHYTHM)
    if rhythm and rhythm.metric.available:
        result.reference_tempo = rhythm.details.get("reference_tempo_bpm")
        result.user_tempo = rhythm.details.get("user_tempo_bpm")

    rows: list[dict] = []

    if result.reference_key or result.user_key:
        rows.append({"id": "key", "label": "Key", "format": "text",
                     "original": result.reference_key, "user": result.user_key, "difference": None})

    if result.reference_tempo or result.user_tempo:
        diff = (
            round(result.user_tempo - result.reference_tempo, 1)
            if result.reference_tempo and result.user_tempo else None
        )
        rows.append({"id": "tempo", "label": "Tempo (BPM)", "format": "number",
                     "original": result.reference_tempo, "user": result.user_tempo, "difference": diff})

    rows.append({"id": "duration", "label": "Duration", "format": "time",
                 "original": round(ref.duration, 1), "user": round(user.duration, 1),
                 "difference": round(user.duration - ref.duration, 1)})

    ref_range, user_range = vocal_range(ref), vocal_range(user)
    if ref_range or user_range:
        fmt = lambda r: f"{r[0]} - {r[1]}" if r else None  # noqa: E731
        rows.append({"id": "vocal_range", "label": "Vocal Range", "format": "text",
                     "original": fmt(ref_range), "user": fmt(user_range), "difference": None})

    pitch = _by_metric(outputs, PITCH_ACCURACY)
    if pitch and pitch.metric.available and pitch.details.get("mean_deviation_cents") is not None:
        rows.append({"id": "pitch_deviation", "label": "Pitch Deviation", "format": "cents",
                     "original": None, "user": pitch.details["mean_deviation_cents"], "difference": None})

    if rhythm and rhythm.metric.available and rhythm.details.get("median_abs_lag_ms") is not None:
        rows.append({"id": "timing_offset", "label": "Timing Offset", "format": "ms",
                     "original": None, "user": rhythm.details.get("mean_lag_ms"), "difference": None})

    stability = _by_metric(outputs, STABILITY)
    if stability and stability.metric.available:
        rows.append({"id": "stability_score", "label": "Stability Score", "format": "score",
                     "original": None, "user": stability.metric.score, "difference": None})

    result.rows = rows
    return result
