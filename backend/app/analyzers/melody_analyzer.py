"""
NAADAMAYA melody matching analyzer.

Implements MelodyAnalyzer. It asks a different question from pitch accuracy:

    pitch accuracy  "Were your notes at the right pitch?"      (absolute, in cents)
    melody matching "Did your melody move the way the original moves?"  (shape)

Because it looks at movement, it is key-independent: the constant offset
between the singer and the reference (any key difference left over after the
alignment engine removed octaves) is subtracted first. A singer who performs
the whole song a tone lower still has a well-matched melody.

This is NOT raga or svara recognition. It compares pitch movement only.
Carnatic, Hindustani and Western analyzers can later implement this same
interface with real musical grammar.

Measured from the aligned pitch:
  - contour correlation: do the two melodies rise and fall together?
  - note agreement: how often is the singer within half a semitone of the
    original note, once the key offset is removed?
  - weak stretches: windows where the melody clearly went a different way

Reliability rules:
  - If alignment found no comparable pitch, the metric is "unavailable".
  - If the original has almost no melodic movement (a near-monotone chant),
    contour comparison is meaningless, so the metric is "unavailable" and
    says why. Pitch accuracy and rhythm still apply to such songs.
  - Too few comparable frames means "Insufficient data for reliable analysis."
"""

import numpy as np

from app.analyzers.interfaces import (
    MELODY_MATCHING,
    REASON_INSUFFICIENT,
    AnalysisInputs,
    AnalyzerOutput,
    Finding,
    MelodyAnalyzer,
    MetricResult,
)
from app.utils.audio_utils import hz_to_midi, linear_score

MIN_CONFIDENCE = 0.5
MIN_COMPARABLE_FRAMES = 80          # about 1.9 s of comparable singing
MIN_MELODIC_RANGE_SEMITONES = 2.0   # original must move at least this much (std, semitones)
MAX_PLAUSIBLE_SEMITONES = 7.0       # larger gaps are tracking errors, not melody

NOTE_MATCH_SEMITONES = 0.5
WINDOW_SECONDS = 2.0
MIN_WINDOW_FRAMES = 15
WEAK_WINDOW_SEMITONES = 1.0         # a window this far off, on average, is flagged
MERGE_GAP_SECONDS = 1.0
MAX_FINDINGS = 6

# Scoring: contour correlation 0.95 or more is 100, 0.30 or less is 0.
CORR_BEST, CORR_WORST = 0.95, 0.30
# Share of frames on the right note: 90% is 100, 30% is 0.
MATCH_BEST, MATCH_WORST = 0.90, 0.30


def _smooth(values: np.ndarray, width: int = 5) -> np.ndarray:
    if values.size < width:
        return values
    return np.convolve(values, np.ones(width) / width, mode="same")


class SignalMelodyAnalyzer(MelodyAnalyzer):
    def analyze(self, inputs: AnalysisInputs) -> AnalyzerOutput:
        alignment = inputs.alignment
        aligned = alignment.aligned_pitch if alignment else None

        if aligned is None:
            reason = alignment.notes[0] if alignment and alignment.notes else REASON_INSUFFICIENT
            return AnalyzerOutput(MetricResult.unavailable(MELODY_MATCHING, reason))

        ref_midi = np.asarray(hz_to_midi(aligned.ref_hz), dtype=float)
        user_midi = np.asarray(hz_to_midi(aligned.user_hz), dtype=float)
        times = aligned.times

        valid = (
            np.isfinite(ref_midi)
            & np.isfinite(user_midi)
            & (aligned.confidence >= MIN_CONFIDENCE)
        )
        if int(valid.sum()) < MIN_COMPARABLE_FRAMES:
            return AnalyzerOutput(MetricResult.unavailable(MELODY_MATCHING, REASON_INSUFFICIENT))

        # Key-independent: remove the constant offset between the two singers.
        offset = float(np.median(user_midi[valid] - ref_midi[valid]))
        diff = user_midi - ref_midi - offset

        # Gaps larger than a fifth are tracking errors, not melody.
        valid &= np.abs(diff) <= MAX_PLAUSIBLE_SEMITONES
        n = int(valid.sum())
        if n < MIN_COMPARABLE_FRAMES:
            return AnalyzerOutput(
                MetricResult.unavailable(
                    MELODY_MATCHING, "The singing could not be matched to the original melody reliably."
                )
            )

        ref_v, user_v = ref_midi[valid], user_midi[valid]

        # A near-monotone original has no melody to compare.
        movement = float(np.std(ref_v))
        if movement < MIN_MELODIC_RANGE_SEMITONES:
            return AnalyzerOutput(
                MetricResult.unavailable(
                    MELODY_MATCHING,
                    "The original has very little melodic movement, so melody matching does not apply.",
                    evidence={"melodic_movement_semitones": round(movement, 2)},
                ),
                details={"melodic_movement_semitones": round(movement, 2)},
            )

        # ---- the two measurements ----
        ref_s, user_s = _smooth(ref_v), _smooth(user_v - offset)
        corr = float(np.corrcoef(ref_s, user_s)[0, 1]) if np.std(user_s) > 1e-6 else 0.0
        if not np.isfinite(corr):
            corr = 0.0

        agreement = float(np.mean(np.abs(diff[valid]) <= NOTE_MATCH_SEMITONES))

        corr_score = linear_score(corr, best=CORR_BEST, worst=CORR_WORST)
        match_score = linear_score(agreement, best=MATCH_BEST, worst=MATCH_WORST)
        score = 0.5 * corr_score + 0.5 * match_score

        # ---- weak stretches ----
        findings: list[Finding] = []
        hop = float(np.median(np.diff(times))) if times.size > 1 else 0.02
        win = max(MIN_WINDOW_FRAMES, int(round(WINDOW_SECONDS / hop)))
        weak: list[list[float]] = []
        for start in range(0, len(times), win):
            sl = slice(start, min(start + win, len(times)))
            vm = valid[sl]
            if int(vm.sum()) < MIN_WINDOW_FRAMES:
                continue
            mean_gap = float(np.mean(np.abs(diff[sl][vm])))
            if mean_gap < WEAK_WINDOW_SEMITONES:
                continue
            t0, t1 = float(times[sl.start]), float(times[sl.stop - 1])
            if weak and t0 - weak[-1][1] <= MERGE_GAP_SECONDS:
                weak[-1][1] = t1
                weak[-1][2] = max(weak[-1][2], mean_gap)
            else:
                weak.append([t0, t1, mean_gap])

        weak.sort(key=lambda w: -w[2])
        for t0, t1, gap in sorted(weak[:MAX_FINDINGS], key=lambda w: w[0]):
            findings.append(
                Finding(
                    kind="melody_mismatch",
                    metric_id=MELODY_MATCHING,
                    start=round(t0, 2),
                    end=round(t1, 2),
                    severity=float(np.clip(gap / 3.0, 0.1, 1.0)),
                    evidence={"mean_gap_semitones": round(gap, 2)},
                    label="Melody differs",
                )
            )

        relevance = "high" if movement >= 3.0 else "medium"
        description = (
            f"Your melody followed the original's movement closely enough to correlate at {corr:.2f}, "
            f"and you were on the right note {agreement * 100:.0f}% of the time."
        )
        metric = MetricResult.measured(
            MELODY_MATCHING,
            score,
            description,
            relevance=relevance,
            evidence={
                "contour_correlation": round(corr, 3),
                "note_agreement_percent": round(agreement * 100, 1),
                "melodic_movement_semitones": round(movement, 2),
                "frames": n,
            },
        )
        return AnalyzerOutput(
            metric=metric,
            findings=findings,
            details={
                "contour_correlation": round(corr, 3),
                "note_agreement_percent": round(agreement * 100, 1),
                "key_offset_semitones": round(offset, 2),
                "melodic_movement_semitones": round(movement, 2),
            },
        )
