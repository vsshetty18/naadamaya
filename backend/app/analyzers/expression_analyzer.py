"""
NAADAMAYA expression & dynamics analyzer.

Implements ExpressionAnalyzer. It measures how similar the singer's LOUDNESS
SHAPE is to the original's. It is a measurement of acoustic dynamics, not of
emotion: nothing here claims to know whether a performance "felt" right, and
the metric is named "Expression & Dynamics" for that reason.

Measured (all in decibels, relative to each recording's own loud parts, so a
louder or quieter microphone does not matter):
  - energy contour correlation: do the two get louder and softer together,
    once the singer is lined up with the original using the alignment path?
  - dynamic range: the spread between soft and loud passages. A singer who
    holds one flat volume has a much narrower range than the original.
  - phrase energy: loudness per section of the song, compared section by
    section, to find stretches that were clearly flatter or harsher.

Reliability rules:
  - Needs a usable alignment path. Without one the metric is "unavailable".
  - If the original itself has almost no dynamic variation (a steady chant),
    there is no contour to compare, so the metric is "unavailable" and says so.
  - Recordings flagged as clipped have unreliable loudness, so the score is
    withheld (clipping flattens peaks and invents false evenness).
  - The reference may include instruments, so its loudness is a mix of voice
    and music. This is stated in the notes. It is the best available
    reference for how the performance should rise and fall.
  - Too little sound means "Insufficient data for reliable analysis."
"""

import librosa
import numpy as np

from app.analyzers.interfaces import (
    EXPRESSION,
    REASON_INSUFFICIENT,
    AnalysisInputs,
    AnalyzerOutput,
    AudioFeatures,
    Finding,
    MetricResult,
    ExpressionAnalyzer,
)
from app.utils.audio_utils import linear_score

FRAME_LENGTH = 2048
HOP_LENGTH = 512
SMOOTH_SECONDS = 0.6
MIN_ACTIVE_FRAMES = 150
MIN_REF_RANGE_DB = 4.0          # the original must vary at least this much (5th to 95th percentile)
MAX_PATH_POINTS_REQUIRED = 20
MIN_QUALITY = 0.25

# Scoring
CORR_BEST, CORR_WORST = 0.85, 0.15
RANGE_BEST_RATIO, RANGE_WORST_RATIO = 1.0, 0.3   # singer range / reference range
CORR_WEIGHT = 0.7

WINDOWS_TARGET_SECONDS = 20.0
MAX_WINDOWS, MIN_WINDOWS = 10, 3
FLAG_DIFF_DB = 6.0
MAX_FINDINGS = 4


def _db_contour(features: AudioFeatures) -> tuple[np.ndarray, np.ndarray]:
    """Loudness in dB per frame (relative to the loud parts) and its frame times."""
    rms = librosa.feature.rms(y=features.samples, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH)[0]
    db = 20.0 * np.log10(np.maximum(rms, 1e-10))
    times = librosa.frames_to_time(np.arange(db.size), sr=features.sample_rate, hop_length=HOP_LENGTH)
    if db.size:
        db = db - float(np.percentile(db, 95))
    return db, times


def _smooth(values: np.ndarray, hop_seconds: float) -> np.ndarray:
    width = max(3, int(round(SMOOTH_SECONDS / hop_seconds)))
    if values.size < width:
        return values
    return np.convolve(values, np.ones(width) / width, mode="same")


def _range_db(values: np.ndarray) -> float:
    return float(np.percentile(values, 95) - np.percentile(values, 5))


class SignalExpressionAnalyzer(ExpressionAnalyzer):
    def analyze(self, inputs: AnalysisInputs) -> AnalyzerOutput:
        alignment = inputs.alignment
        if alignment is None or len(alignment.path) < MAX_PATH_POINTS_REQUIRED or alignment.quality < MIN_QUALITY:
            return AnalyzerOutput(
                MetricResult.unavailable(
                    EXPRESSION,
                    "The singing could not be lined up with the original well enough to compare dynamics.",
                )
            )

        if "clipping" in inputs.user.warnings or "clipping" in inputs.reference.warnings:
            return AnalyzerOutput(
                MetricResult.unavailable(
                    EXPRESSION,
                    "A recording was distorted (too loud), so its loudness changes cannot be compared fairly.",
                )
            )

        ref_db, ref_t = _db_contour(inputs.reference)
        user_db, user_t = _db_contour(inputs.user)
        if ref_db.size < MIN_ACTIVE_FRAMES or user_db.size < MIN_ACTIVE_FRAMES:
            return AnalyzerOutput(MetricResult.unavailable(EXPRESSION, REASON_INSUFFICIENT))

        hop = HOP_LENGTH / float(inputs.reference.sample_rate)
        ref_s, user_s = _smooth(ref_db, hop), _smooth(user_db, hop)

        # Only the part of the reference that the alignment covers.
        path = np.asarray(alignment.path, dtype=float)
        ref_path, user_path = path[:, 0], path[:, 1]
        in_span = (ref_t >= ref_path[0]) & (ref_t <= ref_path[-1])
        if int(in_span.sum()) < MIN_ACTIVE_FRAMES:
            return AnalyzerOutput(MetricResult.unavailable(EXPRESSION, REASON_INSUFFICIENT))

        ref_seg = ref_s[in_span]
        times = ref_t[in_span]

        unique_ref, idx = np.unique(ref_path, return_index=True)
        user_time_for_ref = np.interp(times, unique_ref, user_path[idx])
        user_seg = np.interp(user_time_for_ref, user_t, user_s)

        ref_range = _range_db(ref_seg)
        if ref_range < MIN_REF_RANGE_DB:
            return AnalyzerOutput(
                MetricResult.unavailable(
                    EXPRESSION,
                    "The original has very little loudness variation, so there is no dynamic contour to compare.",
                    evidence={"reference_range_db": round(ref_range, 1)},
                )
            )

        user_range = _range_db(user_seg)
        corr = float(np.corrcoef(ref_seg, user_seg)[0, 1]) if np.std(user_seg) > 1e-6 else 0.0
        if not np.isfinite(corr):
            corr = 0.0
        range_ratio = user_range / ref_range

        corr_score = linear_score(corr, best=CORR_BEST, worst=CORR_WORST)
        range_score = linear_score(min(range_ratio, 1.0 / max(range_ratio, 1e-6)) if range_ratio > 1.0 else range_ratio,
                                   best=RANGE_BEST_RATIO, worst=RANGE_WORST_RATIO)
        score = CORR_WEIGHT * corr_score + (1.0 - CORR_WEIGHT) * range_score

        # ---- per-section loudness differences ----
        span = float(times[-1] - times[0])
        windows = int(np.clip(round(span / WINDOWS_TARGET_SECONDS), MIN_WINDOWS, MAX_WINDOWS))
        edges = np.linspace(times[0], times[-1], windows + 1)
        findings: list[Finding] = []
        for i in range(windows):
            mask = (times >= edges[i]) & (times <= edges[i + 1])
            if int(mask.sum()) < 20:
                continue
            ref_spread = float(np.std(ref_seg[mask]))
            user_spread = float(np.std(user_seg[mask]))
            diff = user_spread - ref_spread
            if ref_spread >= 2.0 and diff <= -FLAG_DIFF_DB / 2:
                findings.append(
                    Finding(
                        kind="energy_flat",
                        metric_id=EXPRESSION,
                        start=round(float(edges[i]), 2),
                        end=round(float(edges[i + 1]), 2),
                        severity=float(np.clip(abs(diff) / 8.0, 0.1, 1.0)),
                        evidence={"reference_variation_db": round(ref_spread, 1), "user_variation_db": round(user_spread, 1)},
                        label="Flat dynamics",
                    )
                )
        findings = sorted(findings, key=lambda f: -f.severity)[:MAX_FINDINGS]
        findings.sort(key=lambda f: f.start)

        notes = ["The original's loudness includes any instruments, so this compares overall rise and fall."]
        if "very_quiet" in inputs.user.warnings:
            notes.append("The recording was very quiet, so loudness changes may be less reliable.")

        description = (
            f"Your loudness followed the original's rise and fall with a correlation of {corr:.2f}, "
            f"using about {range_ratio * 100:.0f}% of its dynamic range."
        )
        metric = MetricResult.measured(
            EXPRESSION,
            score,
            description,
            relevance="medium",
            evidence={
                "energy_correlation": round(corr, 3),
                "dynamic_range_ratio": round(range_ratio, 2),
                "reference_range_db": round(ref_range, 1),
                "user_range_db": round(user_range, 1),
            },
        )
        return AnalyzerOutput(
            metric=metric,
            findings=findings,
            details={
                "energy_correlation": round(corr, 3),
                "dynamic_range_ratio": round(range_ratio, 2),
                "reference_range_db": round(ref_range, 1),
                "user_range_db": round(user_range, 1),
                "notes": notes,
            },
        )
