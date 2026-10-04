"""
NAADAMAYA vocal stability analyzer.

Implements StabilityAnalyzer. It answers: "When you held a note, did it stay
steady?" It looks only at the SINGER's own pitch track. Pitch accuracy
(against the reference) is a separate metric.

How it works:
  1. The singer's voiced pitch is split into notes (a new note starts when the
     pitch moves more than 0.8 semitones away from the note so far).
  2. Only SUSTAINED notes (at least 0.35 s) are judged. Short notes tell us
     nothing about steadiness.
  3. For each sustained note the spread of the pitch around its own centre is
     measured in cents.
  4. Vibrato is recognised and NOT counted as instability. A regular wobble of
     4 to 8 cycles per second is removed before measuring the spread, so a
     singer with a clean vibrato is not punished. What remains (slow drift,
     irregular wobble) is the instability.
  5. The score is the duration-weighted median spread: about 15 cents or less
     is 100, 70 cents or more is 0.

Findings:
  - Unsteady notes (spread of 40 cents or more), with the note name, spread and
    time range on the REFERENCE clock (using the alignment path when there is
    one). Findings in the singer's highest notes are tagged high_note=True so
    the feedback can say "your high notes become unsteady".

Honesty rules:
  - Fewer than 3 sustained notes, or under 3 seconds of them in total, means
    "unavailable". A fast chant with no held notes has nothing to judge, and
    the report says so instead of inventing a number.
  - Tracking noise from a pitch tracker is a few cents, so a "perfect" 100 is
    not expected. A recording marked very_quiet is noted as less reliable.
  - The reference's own steadiness is reported in details for context only.
    It is never scored, because the reference pitch may follow an instrument.
"""

import numpy as np

from app.analyzers.interfaces import (
    REASON_INSUFFICIENT,
    STABILITY,
    AnalysisInputs,
    AnalyzerOutput,
    AudioFeatures,
    Finding,
    MetricResult,
    PitchTrack,
    StabilityAnalyzer,
)
from app.utils.audio_utils import contiguous_regions, hz_to_midi, hz_to_note_name, linear_score

SPLIT_SEMITONES = 0.8            # a jump this big from the note so far starts a new note
MIN_NOTE_SECONDS = 0.35
MIN_VIBRATO_SECONDS = 0.6
MIN_SUSTAINED_NOTES = 3
MIN_SUSTAINED_TOTAL_SECONDS = 3.0

VIBRATO_BAND_HZ = (4.0, 8.0)
VIBRATO_MIN_FRACTION = 0.5       # share of the wobble that must be in the vibrato band
VIBRATO_MIN_EXTENT_CENTS = 30.0  # peak to peak
VIBRATO_MAX_EXTENT_CENTS = 250.0

# Scoring: spread of 15 cents or less is 100, 70 cents or more is 0.
BEST_SPREAD_CENTS = 15.0
WORST_SPREAD_CENTS = 70.0

UNSTEADY_CENTS = 40.0
MERGE_GAP_SECONDS = 1.0
MAX_FINDINGS = 6
HIGH_NOTE_QUANTILE = 0.75
HIGH_NOTE_MIN_NOTES = 4
HELD_SHARE_HIGH_RELEVANCE = 0.35  # held notes make up this much of the singing: stability matters a lot
MAX_NOTE_LIST = 300


# ==========================================================
# Splitting a pitch track into notes
# ==========================================================
def _split_run(midi: np.ndarray) -> list[tuple[int, int]]:
    """Splits one unbroken voiced run into notes. Needs two frames beyond the limit in a row."""
    segments: list[tuple[int, int]] = []
    start, pending = 0, 0
    for i in range(1, len(midi)):
        recent = midi[max(start, i - 7): i]
        if recent.size == 0:
            continue
        pending = pending + 1 if abs(midi[i] - float(np.median(recent))) > SPLIT_SEMITONES else 0
        if pending >= 2:
            cut = i - 1
            if cut - start > 0:
                segments.append((start, cut))
            start, pending = cut, 0
    segments.append((start, len(midi)))
    return segments


def _vibrato(cents: np.ndarray, hop: float) -> tuple[bool, float, float, float]:
    """
    Returns (is_vibrato, vibrato_fraction, rate_hz, extent_cents_peak_to_peak).
    vibrato_fraction is the share of the wobble's power inside the 4 to 8 Hz band.
    """
    n = cents.size
    if n * hop < MIN_VIBRATO_SECONDS:
        return False, 0.0, 0.0, 0.0
    x = cents - cents.mean()
    spectrum = np.abs(np.fft.rfft(x * np.hanning(n))) ** 2
    freqs = np.fft.rfftfreq(n, d=hop)
    total = float(spectrum[1:].sum())
    if total <= 0:
        return False, 0.0, 0.0, 0.0
    band = (freqs >= VIBRATO_BAND_HZ[0]) & (freqs <= VIBRATO_BAND_HZ[1])
    if not band.any():
        return False, 0.0, 0.0, 0.0
    fraction = float(spectrum[band].sum() / total)
    rate = float(freqs[band][np.argmax(spectrum[band])])
    extent = 2.0 * np.sqrt(2.0) * float(x.std()) * np.sqrt(fraction)
    is_vib = (
        fraction >= VIBRATO_MIN_FRACTION
        and VIBRATO_MIN_EXTENT_CENTS <= extent <= VIBRATO_MAX_EXTENT_CENTS
    )
    return is_vib, fraction, rate, extent


def sustained_notes(track: PitchTrack) -> list[dict]:
    """Every sustained note in a pitch track, with its steadiness measurements."""
    hop = track.hop_seconds
    if hop <= 0 or len(track) < 10:
        return []

    midi = np.asarray(hz_to_midi(track.hz), dtype=float)
    min_frames = max(3, int(np.ceil(MIN_NOTE_SECONDS / hop)))
    notes: list[dict] = []

    for run_start, run_end in contiguous_regions(np.isfinite(midi), min_length=min_frames):
        run = midi[run_start:run_end]
        for a, b in _split_run(run):
            if b - a < min_frames:
                continue
            seg = run[a:b]
            centre = float(np.median(seg))
            cents = (seg - centre) * 100.0
            raw_spread = float(cents.std())

            is_vib, fraction, rate, extent = _vibrato(cents, hop)
            # Remove the regular wobble: only what is left counts as instability.
            spread = raw_spread * np.sqrt(max(0.0, 1.0 - fraction)) if is_vib else raw_spread

            i0, i1 = run_start + a, run_start + b
            notes.append(
                {
                    "start": float(track.times[i0]),
                    "end": float(track.times[i1 - 1]),
                    "duration": float(track.times[i1 - 1] - track.times[i0]) + hop,
                    "centre_midi": centre,
                    "spread": spread,
                    "vibrato": is_vib,
                    "vibrato_rate": rate if is_vib else None,
                    "vibrato_extent": extent if is_vib else None,
                }
            )
    return notes


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cumulative = np.cumsum(w)
    return float(v[int(np.searchsorted(cumulative, 0.5 * cumulative[-1]))])


def _to_reference_clock(alignment, user_time: float) -> float:
    """Moves a time in the singer's recording onto the reference clock."""
    if alignment is None or len(alignment.path) < 2:
        return user_time
    path = np.asarray(alignment.path, dtype=float)
    user_t, ref_t = path[:, 1], path[:, 0]
    unique_user, idx = np.unique(user_t, return_index=True)
    if unique_user.size < 2:
        return user_time
    return float(np.interp(user_time, unique_user, ref_t[idx]))


def _held_share(features: AudioFeatures) -> float | None:
    """How much of the voiced singing is held notes (a slow, sustained song has a lot)."""
    if features.pitch is None:
        return None
    voiced = float(features.pitch.voiced.sum()) * features.pitch.hop_seconds
    if voiced <= 0:
        return None
    return sum(n["duration"] for n in sustained_notes(features.pitch)) / voiced


# ==========================================================
# The analyzer
# ==========================================================
class SignalStabilityAnalyzer(StabilityAnalyzer):
    def analyze(self, inputs: AnalysisInputs) -> AnalyzerOutput:
        track = inputs.user.pitch
        if track is None:
            return AnalyzerOutput(MetricResult.unavailable(STABILITY, REASON_INSUFFICIENT))

        notes = sustained_notes(track)
        total = sum(n["duration"] for n in notes)
        if len(notes) < MIN_SUSTAINED_NOTES or total < MIN_SUSTAINED_TOTAL_SECONDS:
            return AnalyzerOutput(
                MetricResult.unavailable(
                    STABILITY,
                    "There were too few held notes to judge steadiness reliably.",
                    evidence={"sustained_notes": len(notes), "sustained_seconds": round(total, 1)},
                )
            )

        spreads = np.array([n["spread"] for n in notes])
        weights = np.array([n["duration"] for n in notes])
        typical = _weighted_median(spreads, weights)
        score = linear_score(typical, best=BEST_SPREAD_CENTS, worst=WORST_SPREAD_CENTS)

        # ---- the singer's highest notes ----
        pitches = np.array([n["centre_midi"] for n in notes])
        high_cut = float(np.quantile(pitches, HIGH_NOTE_QUANTILE))
        is_high = pitches >= high_cut
        high_spread = (
            round(_weighted_median(spreads[is_high], weights[is_high]), 1)
            if int(is_high.sum()) >= HIGH_NOTE_MIN_NOTES - 1 and len(notes) >= HIGH_NOTE_MIN_NOTES
            else None
        )

        # ---- findings: unsteady notes, merged when close together ----
        alignment = inputs.alignment
        groups: list[dict] = []
        for note, high in zip(notes, is_high):
            if note["spread"] < UNSTEADY_CENTS:
                continue
            start = _to_reference_clock(alignment, note["start"])
            end = max(start, _to_reference_clock(alignment, note["end"]))
            if groups and start - groups[-1]["end"] <= MERGE_GAP_SECONDS:
                g = groups[-1]
                g["end"] = max(g["end"], end)
                g["spread"] = max(g["spread"], note["spread"])
                g["high"] = g["high"] or bool(high)
                g["count"] += 1
            else:
                groups.append(
                    {
                        "start": start,
                        "end": end,
                        "spread": note["spread"],
                        "high": bool(high),
                        "count": 1,
                        "note": hz_to_note_name(float(2 ** ((note["centre_midi"] - 69) / 12) * 440.0)),
                    }
                )

        groups.sort(key=lambda g: -g["spread"])
        findings = [
            Finding(
                kind="unstable_note",
                metric_id=STABILITY,
                start=round(g["start"], 2),
                end=round(g["end"], 2),
                severity=float(np.clip(g["spread"] / 120.0, 0.1, 1.0)),
                evidence={
                    "spread_cents": round(g["spread"]),
                    "note": g["note"],
                    "notes_affected": g["count"],
                    "high_note": g["high"],
                },
                label="Stability issue",
            )
            for g in sorted(groups[:MAX_FINDINGS], key=lambda g: g["start"])
        ]

        # ---- vibrato and context ----
        vib_notes = [n for n in notes if n["vibrato"]]
        vib_share = sum(n["duration"] for n in vib_notes) / total
        reference_spread = None
        if inputs.reference.pitch is not None:
            ref_notes = sustained_notes(inputs.reference.pitch)
            if len(ref_notes) >= MIN_SUSTAINED_NOTES:
                reference_spread = round(
                    _weighted_median(
                        np.array([n["spread"] for n in ref_notes]),
                        np.array([n["duration"] for n in ref_notes]),
                    ),
                    1,
                )

        held = _held_share(inputs.reference)
        relevance = "high" if (held is not None and held >= HELD_SHARE_HIGH_RELEVANCE) else "medium"

        notes_out = []
        if "very_quiet" in inputs.user.warnings:
            notes_out.append("The recording was very quiet, so pitch tracking may be less reliable.")
        if "clipping" in inputs.user.warnings:
            notes_out.append("The recording was distorted (too loud), which can affect pitch tracking.")

        description = (
            f"Held notes wavered by about {round(typical)} cents on average"
            + (f", with a regular vibrato on {vib_share * 100:.0f}% of them (not counted against you)."
               if vib_share >= 0.15 else ".")
        )
        metric = MetricResult.measured(
            STABILITY,
            score,
            description,
            relevance=relevance,
            evidence={
                "typical_spread_cents": round(typical, 1),
                "sustained_notes": len(notes),
                "sustained_seconds": round(total, 1),
                "high_note_spread_cents": high_spread,
            },
        )
        return AnalyzerOutput(
            metric=metric,
            findings=findings,
            details={
                "typical_spread_cents": round(typical, 1),
                "high_note_spread_cents": high_spread,
                "reference_spread_cents": reference_spread,  # context only, never scored
                "sustained_note_count": len(notes),
                "sustained_seconds": round(total, 1),
                "vibrato_share": round(vib_share, 2),
                "vibrato_rate_hz": (
                    round(float(np.median([n["vibrato_rate"] for n in vib_notes])), 1) if vib_notes else None
                ),
                "vibrato_extent_cents": (
                    round(float(np.median([n["vibrato_extent"] for n in vib_notes]))) if vib_notes else None
                ),
                # For per-section scores: each note on the reference clock with its spread.
                "notes": [
                    {
                        "start": round(_to_reference_clock(alignment, n["start"]), 2),
                        "end": round(_to_reference_clock(alignment, n["end"]), 2),
                        "spread_cents": round(n["spread"], 1),
                    }
                    for n in notes[:MAX_NOTE_LIST]
                ],
                "reliability_notes": notes_out,
            },
        )
