"""
NAADAMAYA rhythm and timing analyzer.

Implements RhythmAnalyzer. It reads the time alignment produced by the
alignment engine: the path of matched (reference_seconds, singer_seconds)
points. For each moment it asks how far behind or ahead of the original the
singer was.

    lag = singer_time - reference_time - start_offset

`start_offset` (when the singer began, relative to the original) is removed
first, because the singer pressed record at an arbitrary moment. That is not
a timing mistake. Everything after that first sound is.

Positive lag = late, negative = early.

Measured:
  - typical lag across the song (median absolute, in milliseconds)
  - lag per stretch of the song (late or early entries)
  - tempo drift: does the lag keep growing? (a singer who is slower or
    faster than the original drifts steadily)
  - tempo ratio (singer's sung duration / the original's)
  - tempo estimates (BPM) for the two recordings, as information only

Outputs for the report:
  details["rhythm_comparison"] = {"unit": "ms", "entries": [{label, startTime, offsetMs}]}
  This is the shape the frontend Rhythm Comparison card already renders.

Honesty rules:
  - The path comes from dynamic time warping, which can partly "absorb" timing
    errors when the match is poor. If alignment quality is low, or the path is
    too short, the metric is "unavailable" instead of a flattering score.
  - Tempo (BPM) from audio is unreliable for singing and is often off by a
    factor of two. It is reported in details only, never scored.
  - No beat grid is claimed for songs without a clear pulse: the score is
    about timing relative to the original, not a metronome.
"""

import librosa
import numpy as np

from app.analyzers.interfaces import (
    RHYTHM,
    REASON_INSUFFICIENT,
    AnalysisInputs,
    AnalyzerOutput,
    AudioFeatures,
    Finding,
    MetricResult,
    RhythmAnalyzer,
)
from app.utils.audio_utils import format_duration, linear_score

MIN_PATH_POINTS = 20
MIN_QUALITY = 0.25
MIN_SPAN_SECONDS = 6.0

# Scoring: median lag of 80 ms or less scores 100, 600 ms or more scores 0.
BEST_LAG_SECONDS = 0.08
WORST_LAG_SECONDS = 0.60

FLAG_LAG_SECONDS = 0.15          # a stretch this far off is flagged
TEMPO_DRIFT_SECONDS = 0.8        # total drift across the song worth mentioning
TEMPO_RATIO_FLAG = 0.06          # 6% faster or slower than the original
HIGH_ONSET_RATE = 2.5            # onsets per active second: a busy, rhythmic song

MAX_WINDOWS = 8
MIN_WINDOWS = 2
WINDOW_TARGET_SECONDS = 25.0


def _bpm(features: AudioFeatures) -> float | None:
    """Rough tempo estimate. Informational only: often wrong for singing."""
    try:
        start = int(max(0.0, features.active_regions[0][0]) * features.sample_rate) if features.active_regions else 0
        y = features.samples[start:]
        if y.size < features.sample_rate * 5:
            return None
        envelope = librosa.onset.onset_strength(y=y, sr=features.sample_rate)
        value = librosa.feature.rhythm.tempo(onset_envelope=envelope, sr=features.sample_rate)
        bpm = float(np.atleast_1d(value)[0])
        return round(bpm, 1) if np.isfinite(bpm) and bpm > 0 else None
    except Exception:  # noqa: BLE001 - tempo is optional information
        return None


def _onset_rate(features: AudioFeatures) -> float | None:
    """Note/syllable starts per second of sound. High = a busy, rhythmic song."""
    try:
        active = sum(e - s for s, e in features.active_regions)
        if active < 3.0:
            return None
        onsets = librosa.onset.onset_detect(y=features.samples, sr=features.sample_rate, units="time")
        return round(float(len(onsets) / active), 2)
    except Exception:  # noqa: BLE001
        return None


def _label(start: float, end: float) -> str:
    return f"{format_duration(start)}\u2013{format_duration(end)}"


class SignalRhythmAnalyzer(RhythmAnalyzer):
    def analyze(self, inputs: AnalysisInputs) -> AnalyzerOutput:
        alignment = inputs.alignment
        if alignment is None or len(alignment.path) < MIN_PATH_POINTS:
            return AnalyzerOutput(MetricResult.unavailable(RHYTHM, REASON_INSUFFICIENT))

        if alignment.quality < MIN_QUALITY:
            return AnalyzerOutput(
                MetricResult.unavailable(
                    RHYTHM,
                    "The singing could not be lined up with the original well enough to judge timing.",
                    evidence={"alignment_quality": round(alignment.quality, 2)},
                )
            )

        path = np.asarray(alignment.path, dtype=float)
        ref_t, user_t = path[:, 0], path[:, 1]
        span = float(ref_t[-1] - ref_t[0])
        if span < MIN_SPAN_SECONDS:
            return AnalyzerOutput(MetricResult.unavailable(RHYTHM, REASON_INSUFFICIENT))

        lag = user_t - ref_t - float(alignment.start_offset)   # seconds, + = late
        median_abs_lag = float(np.median(np.abs(lag)))
        score = linear_score(median_abs_lag, best=BEST_LAG_SECONDS, worst=WORST_LAG_SECONDS)

        findings: list[Finding] = []

        # ---- lag per stretch of the song ----
        windows = int(np.clip(round(span / WINDOW_TARGET_SECONDS), MIN_WINDOWS, MAX_WINDOWS))
        edges = np.linspace(ref_t[0], ref_t[-1], windows + 1)
        entries: list[dict] = []
        for i in range(windows):
            last = i == windows - 1
            mask = (ref_t >= edges[i]) & ((ref_t <= edges[i + 1]) if last else (ref_t < edges[i + 1]))
            if int(mask.sum()) < 3:
                continue
            start, end = float(edges[i]), float(edges[i + 1])
            window_lag = float(np.median(lag[mask]))
            entries.append(
                {
                    "label": _label(start, end),
                    "startTime": round(start, 2),
                    "offsetMs": int(round(window_lag * 1000)),
                }
            )
            if abs(window_lag) >= FLAG_LAG_SECONDS:
                late = window_lag > 0
                findings.append(
                    Finding(
                        kind="late_entry" if late else "early_entry",
                        metric_id=RHYTHM,
                        start=round(start, 2),
                        end=round(end, 2),
                        severity=float(np.clip(abs(window_lag) / 0.6, 0.1, 1.0)),
                        evidence={"offset_ms": int(round(window_lag * 1000))},
                        label="Late entries" if late else "Early entries",
                    )
                )

        # ---- tempo drift: does the lag keep growing? ----
        slope = float(np.polyfit(ref_t, lag, 1)[0])        # seconds of lag gained per second
        drift_total = slope * span
        if abs(drift_total) >= TEMPO_DRIFT_SECONDS:
            slowing = drift_total > 0
            findings.append(
                Finding(
                    kind="tempo_drift",
                    metric_id=RHYTHM,
                    start=round(float(ref_t[0]), 2),
                    end=round(float(ref_t[-1]), 2),
                    severity=float(np.clip(abs(drift_total) / 3.0, 0.1, 1.0)),
                    evidence={
                        "drift_seconds": round(drift_total, 2),
                        "direction": "slowing" if slowing else "rushing",
                    },
                    label="Tempo drifted",
                )
            )

        # ---- overall tempo against the original ----
        ratio = alignment.tempo_ratio
        if ratio is not None and abs(ratio - 1.0) >= TEMPO_RATIO_FLAG and abs(drift_total) < TEMPO_DRIFT_SECONDS:
            findings.append(
                Finding(
                    kind="tempo_off",
                    metric_id=RHYTHM,
                    start=round(float(ref_t[0]), 2),
                    end=round(float(ref_t[-1]), 2),
                    severity=float(np.clip(abs(ratio - 1.0) / 0.3, 0.1, 1.0)),
                    evidence={
                        "tempo_ratio": round(ratio, 3),
                        "direction": "slower" if ratio > 1.0 else "faster",
                    },
                    label="Different tempo",
                )
            )

        ref_bpm, user_bpm = _bpm(inputs.reference), _bpm(inputs.user)
        onset_rate = _onset_rate(inputs.reference)
        relevance = "high" if (onset_rate is not None and onset_rate >= HIGH_ONSET_RATE) else "medium"

        late_share = float(np.mean(lag > FLAG_LAG_SECONDS))
        early_share = float(np.mean(lag < -FLAG_LAG_SECONDS))
        description = (
            f"You were typically about {round(median_abs_lag * 1000)} ms away from the original's timing"
            + (f", late for {late_share * 100:.0f}% of the song." if late_share >= early_share and late_share > 0.1
               else f", early for {early_share * 100:.0f}% of the song." if early_share > 0.1
               else ".")
        )

        metric = MetricResult.measured(
            RHYTHM,
            score,
            description,
            relevance=relevance,
            evidence={
                "median_abs_lag_ms": round(median_abs_lag * 1000),
                "drift_seconds": round(drift_total, 2),
                "tempo_ratio": round(ratio, 3) if ratio is not None else None,
                "alignment_quality": round(alignment.quality, 2),
            },
        )
        return AnalyzerOutput(
            metric=metric,
            findings=findings,
            details={
                "rhythm_comparison": {"unit": "ms", "entries": entries},
                "median_abs_lag_ms": round(median_abs_lag * 1000),
                "mean_lag_ms": round(float(np.mean(lag)) * 1000),
                "drift_seconds": round(drift_total, 2),
                "tempo_ratio": round(ratio, 3) if ratio is not None else None,
                "reference_tempo_bpm": ref_bpm,   # information only, often unreliable for singing
                "user_tempo_bpm": user_bpm,
                "onset_rate": onset_rate,
            },
        )
