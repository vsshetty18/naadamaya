"""
NAADAMAYA pitch accuracy analyzer.

Implements PitchAnalyzer. It reads the AlignedPitch produced by the alignment
engine and measures how far the singer's notes are from the reference, in
cents (100 cents = one semitone). Everything reported comes from those
measurements.

What it produces:
  - ONE MetricResult "pitch_accuracy" (0..100), or "unavailable" with a reason
  - Findings: stretches where the singer was clearly sharp, flat or unsteady,
    each with the measured cents and the time range
  - details: the data the report needs for the pitch graph and summary
      pitch_points      [{t, ref_hz, user_hz, ref_midi, user_midi, deviation_cents, confidence}]
      annotations       [{startTime, endTime, type, cents, label}]
      stats             {matched_percent, sharp_percent, flat_percent}
      mean_deviation_cents, median_abs_error_cents
      high_note_error_cents, low_note_error_cents (None if too little data)
      notes             plain statements about reliability

Reliability rules:
  - A frame counts only if BOTH sides had a reliable pitch and its tracker
    confidence is at least MIN_CONFIDENCE.
  - Deviations beyond MAX_PLAUSIBLE_CENTS (a third of an octave) are treated as
    tracking errors or a different melody, not as a real singing mistake. They
    are excluded from the score, and if too many frames are like that the
    metric is "unavailable".
  - If the singer is in a different key (details["key_offset_semitones"] from
    the alignment engine), every note would look wrong, so the metric is
    "unavailable" and says so instead of giving a misleading low score.
  - Too few comparable frames means "Insufficient data for reliable analysis."
"""

import numpy as np

from app.analyzers.interfaces import (
    PITCH_ACCURACY,
    REASON_INSUFFICIENT,
    AnalysisInputs,
    AnalyzerOutput,
    Finding,
    MetricResult,
    PitchAnalyzer,
)
from app.utils.audio_utils import contiguous_regions, hz_to_midi, linear_score

MIN_CONFIDENCE = 0.5
MIN_COMPARABLE_FRAMES = 60          # about 1.4 s of comparable singing
MAX_PLAUSIBLE_CENTS = 400.0
MAX_IMPLAUSIBLE_RATIO = 0.35        # more than this and the data is not trustworthy
KEY_OFFSET_LIMIT_SEMITONES = 0.7

ON_PITCH_CENTS = 25.0               # within this counts as matched
SHARP_FLAT_CENTS = 35.0             # a stretch must average beyond this to be flagged
MIN_STRETCH_SECONDS = 0.6
MERGE_GAP_SECONDS = 0.4
UNSTABLE_STD_CENTS = 45.0

# Scoring: median error of 10 cents or less is 100, 100 cents or more is 0.
BEST_ERROR_CENTS = 10.0
WORST_ERROR_CENTS = 100.0

MAX_GRAPH_POINTS = 300


def _stretches(mask: np.ndarray, times: np.ndarray, min_seconds: float, merge_gap: float):
    """Runs of True as (start_s, end_s), merging short gaps and dropping short runs."""
    hop = float(np.median(np.diff(times))) if times.size > 1 else 0.02
    runs = [(int(s), int(e)) for s, e in contiguous_regions(mask, min_length=1)]
    merged: list[list[int]] = []
    for s, e in runs:
        if merged and (s - merged[-1][1]) * hop <= merge_gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    out = []
    for s, e in merged:
        if (e - s) * hop >= min_seconds:
            out.append((s, e))
    return out


class SignalPitchAnalyzer(PitchAnalyzer):
    def analyze(self, inputs: AnalysisInputs) -> AnalyzerOutput:
        alignment = inputs.alignment
        aligned = alignment.aligned_pitch if alignment else None

        if aligned is None:
            reason = (alignment.notes[0] if alignment and alignment.notes else REASON_INSUFFICIENT)
            return AnalyzerOutput(MetricResult.unavailable(PITCH_ACCURACY, reason))

        key_offset = float((alignment.details or {}).get("key_offset_semitones", 0.0))
        if abs(key_offset) > KEY_OFFSET_LIMIT_SEMITONES:
            return AnalyzerOutput(
                MetricResult.unavailable(
                    PITCH_ACCURACY,
                    f"You seem to be singing in a different key (about {key_offset:+.1f} semitones), "
                    "so note-by-note pitch accuracy cannot be judged fairly.",
                    evidence={"key_offset_semitones": round(key_offset, 2)},
                ),
                details={"key_offset_semitones": round(key_offset, 2)},
            )

        times = aligned.times
        dev = aligned.deviation_cents
        usable = np.isfinite(dev) & (aligned.confidence >= MIN_CONFIDENCE)
        total_usable = int(usable.sum())
        if total_usable < MIN_COMPARABLE_FRAMES:
            return AnalyzerOutput(MetricResult.unavailable(PITCH_ACCURACY, REASON_INSUFFICIENT))

        implausible = usable & (np.abs(dev) > MAX_PLAUSIBLE_CENTS)
        if implausible.sum() / total_usable > MAX_IMPLAUSIBLE_RATIO:
            return AnalyzerOutput(
                MetricResult.unavailable(
                    PITCH_ACCURACY,
                    "The singing could not be matched to the original melody reliably.",
                    evidence={"implausible_ratio": round(float(implausible.sum() / total_usable), 2)},
                )
            )

        valid = usable & ~implausible
        if int(valid.sum()) < MIN_COMPARABLE_FRAMES:
            return AnalyzerOutput(MetricResult.unavailable(PITCH_ACCURACY, REASON_INSUFFICIENT))

        errors = np.abs(dev[valid])
        median_error = float(np.median(errors))
        mean_dev = float(np.mean(dev[valid]))
        score = linear_score(median_error, best=BEST_ERROR_CENTS, worst=WORST_ERROR_CENTS)

        # ---- shares of matched / sharp / flat ----
        n = int(valid.sum())
        matched = int((errors <= ON_PITCH_CENTS).sum())
        sharp = int((dev[valid] > ON_PITCH_CENTS).sum())
        flat = int((dev[valid] < -ON_PITCH_CENTS).sum())
        stats = {
            "matched_percent": round(100.0 * matched / n, 1),
            "sharp_percent": round(100.0 * sharp / n, 1),
            "flat_percent": round(100.0 * flat / n, 1),
        }

        # ---- high and low notes (top and bottom quarter of the reference range) ----
        ref_midi = np.asarray(hz_to_midi(aligned.ref_hz), dtype=float)
        high_err = low_err = None
        vm = ref_midi[valid]
        if n >= 80:
            hi_cut, lo_cut = np.percentile(vm, 75), np.percentile(vm, 25)
            hi_mask, lo_mask = vm >= hi_cut, vm <= lo_cut
            if hi_mask.sum() >= 20:
                high_err = round(float(np.median(errors[hi_mask])), 1)
            if lo_mask.sum() >= 20:
                low_err = round(float(np.median(errors[lo_mask])), 1)

        # ---- findings: sharp, flat and unsteady stretches ----
        findings: list[Finding] = []
        annotations: list[dict] = []
        clean_dev = np.where(valid, dev, np.nan)

        def add_stretches(mask, kind, label):
            for s, e in _stretches(mask, times, MIN_STRETCH_SECONDS, MERGE_GAP_SECONDS):
                seg = clean_dev[s:e]
                seg = seg[np.isfinite(seg)]
                if seg.size < 5:
                    continue
                cents = float(np.mean(seg))
                if kind != "unstable" and abs(cents) < SHARP_FLAT_CENTS:
                    continue
                start, end = float(times[s]), float(times[min(e, len(times)) - 1])
                severity = float(np.clip(abs(cents) / 150.0, 0.1, 1.0)) if kind != "unstable" else float(
                    np.clip(np.std(seg) / 120.0, 0.1, 1.0)
                )
                findings.append(
                    Finding(
                        kind=f"pitch_{kind}",
                        metric_id=PITCH_ACCURACY,
                        start=round(start, 2),
                        end=round(end, 2),
                        severity=severity,
                        evidence={"cents": round(cents), "std_cents": round(float(np.std(seg)), 1)},
                        label=label,
                    )
                )
                annotations.append(
                    {
                        "startTime": round(start, 2),
                        "endTime": round(end, 2),
                        "type": kind,
                        "cents": round(cents),
                        "label": f"{label} (about {abs(round(cents))} cents)" if kind != "unstable" else label,
                    }
                )

        smooth = np.convolve(np.nan_to_num(clean_dev, nan=0.0), np.ones(9) / 9.0, mode="same")
        known = np.isfinite(clean_dev)
        add_stretches(known & (smooth > SHARP_FLAT_CENTS), "sharp", "Sharp")
        add_stretches(known & (smooth < -SHARP_FLAT_CENTS), "flat", "Flat")

        # unsteady = high local spread even when the average is close
        local_std = np.zeros_like(clean_dev)
        for i in range(0, len(clean_dev)):
            seg = clean_dev[max(0, i - 8): i + 9]
            seg = seg[np.isfinite(seg)]
            local_std[i] = np.std(seg) if seg.size >= 6 else 0.0
        add_stretches(known & (local_std > UNSTABLE_STD_CENTS), "unstable", "Unsteady pitch")

        annotations.sort(key=lambda a: a["startTime"])
        findings.sort(key=lambda f: f.start)

        # ---- graph points (thinned) ----
        idx = np.unique(np.linspace(0, len(times) - 1, min(MAX_GRAPH_POINTS, len(times))).round().astype(int))
        user_midi = np.asarray(hz_to_midi(aligned.user_hz), dtype=float)
        points = []
        for i in idx:
            def num(x, digits):
                return round(float(x), digits) if np.isfinite(x) else None

            points.append(
                {
                    "t": round(float(times[i]), 2),
                    "ref_hz": num(aligned.ref_hz[i], 1),
                    "user_hz": num(aligned.user_hz[i], 1),
                    "ref_midi": num(ref_midi[i], 2),
                    "user_midi": num(user_midi[i], 2),
                    "deviation_cents": num(dev[i], 0) if valid[i] else None,
                    "confidence": num(aligned.confidence[i], 2),
                }
            )

        reliability_notes = list(alignment.notes)
        if implausible.any():
            reliability_notes.append(
                f"{int(implausible.sum())} moments were left out because they looked like tracking errors."
            )
        if total_usable / max(1, len(times)) < 0.3:
            reliability_notes.append("Only part of the song had clear pitch, so this score reflects those parts.")

        description = (
            f"Typical difference from the original was about {round(median_error)} cents "
            f"({stats['matched_percent']:.0f}% of the time within {int(ON_PITCH_CENTS)} cents)."
        )

        metric = MetricResult.measured(
            PITCH_ACCURACY,
            score,
            description,
            evidence={"median_abs_error_cents": round(median_error, 1), "frames": n},
        )
        return AnalyzerOutput(
            metric=metric,
            findings=findings,
            details={
                "pitch_points": points,
                "annotations": annotations,
                "stats": stats,
                "mean_deviation_cents": round(mean_dev),
                "median_abs_error_cents": round(median_error, 1),
                "high_note_error_cents": high_err,
                "low_note_error_cents": low_err,
                "notes": reliability_notes,
                "octave_shift": (alignment.details or {}).get("octave_shift", 0),
            },
        )
