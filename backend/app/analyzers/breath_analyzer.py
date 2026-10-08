"""
NAADAMAYA breath consistency analyzer.

Implements BreathAnalyzer. The metric is called "Breath Consistency" and uses
audio-based indicators only. It makes no medical or physiological claims: it
cannot hear breathing, it can only hear what happens to the voice.

What it measures, per sung phrase (a stretch of sound between pauses in the
singer's recording):
  - LOUDNESS FADE: how much quieter the end of the phrase is than its middle.
  - PITCH SAG: how much flatter the singer is in the last half second than in
    the body of the phrase. This is measured against the REFERENCE (using the
    alignment engine's deviation from the original), so a melody that
    naturally falls at the end of a line is not mistaken for a sag. A constant
    key difference cancels out too.

A phrase whose end fades or sags clearly is marked "strained". Others are
"steady". The score comes from the duration-weighted share of badness across
all phrases.

Output for the report:
  details["breath_analysis"] = {"phrases": [{startTime, endTime, status, note}]}
  (times on the REFERENCE clock; this is the shape the frontend Breath Control
  card already renders)

Honesty rules:
  - Fewer than 3 phrases of at least 1.5 s means "unavailable". A fast chant
    or a recording sung over continuous music has no clear phrases to judge.
  - A phrase can end softly on purpose (an artistic decay). The measurement
    cannot know that, so only a LARGE fade or sag is flagged.
  - Pauses are not judged as "taking a breath in the wrong place". That would
    need to know where the original breathes, which the MVP cannot tell
    reliably (the original may include instruments). So there is no "short
    phrase" status yet.
  - Recordings made over backing music have no real pauses, so phrase
    detection will find few phrases and the metric will be unavailable.
"""

import librosa
import numpy as np

from app.analyzers.interfaces import (
    BREATH_CONTROL,
    REASON_BREATH,
    AnalysisInputs,
    AnalyzerOutput,
    BreathAnalyzer,
    Finding,
    MetricResult,
)
from app.utils.audio_utils import linear_score

FRAME_LENGTH = 2048
HOP_LENGTH = 512

MIN_PHRASE_SECONDS = 1.5
MIN_PHRASES = 3
MIN_CONFIDENCE = 0.5

TAIL_SECONDS = 0.5
MIN_TAIL_FRAMES = 4
MIN_BODY_FRAMES = 6

# Badness 0..1 from each measurement
SAG_START_CENTS, SAG_SPAN_CENTS = 10.0, 50.0     # 10 cents sag = 0, 60 cents = 1
FADE_START_DB, FADE_SPAN_DB = 2.0, 10.0          # 2 dB fade = 0, 12 dB = 1
STRAINED_BADNESS = 0.6

# Scoring on the duration-weighted mean badness
BEST_BADNESS, WORST_BADNESS = 0.05, 0.60

LONG_PHRASE_SECONDS = 8.0
MEDIAN_PHRASE_HIGH_RELEVANCE = 5.0
MAX_LISTED_PHRASES = 8


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


def _db_contour(samples: np.ndarray) -> np.ndarray:
    rms = librosa.feature.rms(y=samples, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH)[0]
    return 20.0 * np.log10(np.maximum(rms, 1e-10))


def _clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _note(status: str, fade: float, sag: float | None) -> str:
    if status == "strained":
        parts = []
        if sag is not None and sag >= SAG_START_CENTS + 20:
            parts.append(f"pitch sagged about {round(sag)} cents toward the end")
        if fade >= FADE_START_DB + 6:
            parts.append(f"loudness dropped about {round(fade)} dB toward the end")
        return ("The " + " and ".join(parts) + " of this phrase.").replace("The pitch", "The pitch", 1) \
            if parts else "The end of this phrase weakened."
    return "The phrase stayed even from start to finish."


class SignalBreathAnalyzer(BreathAnalyzer):
    def analyze(self, inputs: AnalysisInputs) -> AnalyzerOutput:
        user = inputs.user
        phrases = [(s, e) for s, e in user.active_regions if e - s >= MIN_PHRASE_SECONDS]
        if len(phrases) < MIN_PHRASES:
            return AnalyzerOutput(
                MetricResult.unavailable(
                    BREATH_CONTROL,
                    REASON_BREATH,
                    evidence={"phrases_found": len(phrases)},
                )
            )

        db = _db_contour(user.samples)
        hop = HOP_LENGTH / float(user.sample_rate)

        alignment = inputs.alignment
        aligned = alignment.aligned_pitch if alignment else None
        dev_times = dev_values = None
        if aligned is not None:
            ok = np.isfinite(aligned.deviation_cents) & (aligned.confidence >= MIN_CONFIDENCE)
            dev_times, dev_values = aligned.times[ok], aligned.deviation_cents[ok]

        rows: list[dict] = []
        for start, end in phrases:
            i0, i1 = int(start / hop), min(int(end / hop), db.size)
            n = i1 - i0
            if n < 12:
                continue

            body_db = float(np.median(db[i0 + int(0.25 * n): i0 + int(0.70 * n)]))
            tail_n = max(3, int(0.15 * n))
            tail_db = float(np.median(db[i1 - tail_n: i1]))
            fade = max(0.0, body_db - tail_db)

            sag = None
            ref_start = _to_reference_clock(alignment, start)
            ref_end = max(ref_start, _to_reference_clock(alignment, end))
            if dev_times is not None and ref_end - ref_start >= MIN_PHRASE_SECONDS * 0.5:
                length = ref_end - ref_start
                in_phrase = (dev_times >= ref_start) & (dev_times <= ref_end)
                body = in_phrase & (dev_times >= ref_start + 0.10 * length) & (dev_times <= ref_start + 0.70 * length)
                tail = in_phrase & (dev_times >= ref_end - TAIL_SECONDS)
                if int(body.sum()) >= MIN_BODY_FRAMES and int(tail.sum()) >= MIN_TAIL_FRAMES:
                    sag = float(np.median(dev_values[body]) - np.median(dev_values[tail]))

            badness = _clip01((fade - FADE_START_DB) / FADE_SPAN_DB)
            if sag is not None:
                badness = max(badness, _clip01((sag - SAG_START_CENTS) / SAG_SPAN_CENTS))

            status = "strained" if badness >= STRAINED_BADNESS else "steady"
            rows.append(
                {
                    "ref_start": ref_start,
                    "ref_end": ref_end,
                    "seconds": end - start,
                    "fade": fade,
                    "sag": sag,
                    "badness": badness,
                    "status": status,
                }
            )

        if len(rows) < MIN_PHRASES:
            return AnalyzerOutput(
                MetricResult.unavailable(BREATH_CONTROL, REASON_BREATH, evidence={"phrases_found": len(rows)})
            )

        weights = np.array([r["seconds"] for r in rows])
        bad = np.array([r["badness"] for r in rows])
        mean_bad = float(np.average(bad, weights=weights))
        score = linear_score(mean_bad, best=BEST_BADNESS, worst=WORST_BADNESS)

        # ---- findings: strained phrases ----
        findings = [
            Finding(
                kind="breath_strained",
                metric_id=BREATH_CONTROL,
                start=round(r["ref_start"], 2),
                end=round(r["ref_end"], 2),
                severity=float(np.clip(r["badness"], 0.1, 1.0)),
                evidence={
                    "phrase_seconds": round(r["seconds"], 1),
                    "fade_db": round(r["fade"], 1),
                    "tail_sag_cents": round(r["sag"]) if r["sag"] is not None else None,
                },
                label="Breath support",
            )
            for r in rows
            if r["status"] == "strained"
        ]

        # ---- phrase list for the report: all strained, then the longest steady ones ----
        strained_rows = [r for r in rows if r["status"] == "strained"]
        steady_rows = sorted((r for r in rows if r["status"] == "steady"), key=lambda r: -r["seconds"])
        chosen = (strained_rows + steady_rows)[:MAX_LISTED_PHRASES]
        chosen.sort(key=lambda r: r["ref_start"])
        phrase_list = [
            {
                "startTime": round(r["ref_start"], 2),
                "endTime": round(r["ref_end"], 2),
                "status": r["status"],
                "note": _note(r["status"], r["fade"], r["sag"]),
            }
            for r in chosen
        ]

        lengths = np.array([r["seconds"] for r in rows])
        median_len, longest = float(np.median(lengths)), float(lengths.max())
        relevance = "high" if (longest >= LONG_PHRASE_SECONDS or median_len >= MEDIAN_PHRASE_HIGH_RELEVANCE) else "medium"

        notes = ["Based on how loudness and pitch behave at the end of each phrase. It cannot hear breathing."]
        if aligned is None:
            notes.append("Pitch could not be compared with the original, so only loudness was used.")
        if "very_quiet" in user.warnings:
            notes.append("The recording was very quiet, so loudness changes may be less reliable.")

        steady_share = 100.0 * (len(rows) - len(strained_rows)) / len(rows)
        description = (
            f"{steady_share:.0f}% of your {len(rows)} phrases stayed even to the end"
            + (f"; the longest lasted about {longest:.0f} seconds." if longest >= LONG_PHRASE_SECONDS else ".")
        )

        metric = MetricResult.measured(
            BREATH_CONTROL,
            score,
            description,
            relevance=relevance,
            evidence={
                "phrases": len(rows),
                "strained_phrases": len(strained_rows),
                "median_phrase_seconds": round(median_len, 1),
                "longest_phrase_seconds": round(longest, 1),
            },
        )
        return AnalyzerOutput(
            metric=metric,
            findings=findings,
            details={
                "breath_analysis": {"phrases": phrase_list},
                "phrase_count": len(rows),
                "strained_count": len(strained_rows),
                "median_phrase_seconds": round(median_len, 1),
                "longest_phrase_seconds": round(longest, 1),
                "notes": notes,
            },
        )
