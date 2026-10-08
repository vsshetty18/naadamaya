"""
NAADAMAYA song sections (the timeline).

    sections = build_sections(reference, outputs, alignment)

Splits the song into stretches on the REFERENCE clock and scores each stretch
from the measurements the analyzers already made, so the timeline shows WHERE
the singer needs to improve.

HONEST STATUS of the section names:
  The MVP cannot tell a verse from a chorus. Sections are found from changes in
  the original's sound (timbre), then snapped to a pause when one is nearby.
  They are named "Section 1", "Section 2", ... and every section is marked
  is_estimated=True so the report can say so. Real structure labelling
  (Verse, Chorus, Pallavi, Charanam) is a future module.
  If structure detection fails, the song is split into equal parts instead.

Section scores use only what was measured inside the section:
  pitch_score      median pitch error against the original (aligned pitch)
  timing_score     median lag along the alignment path
  stability_score  spread of the held notes inside the section
  score            the average of whichever of these exist

A section with no measurable data has score=None and status="unknown". It is
never given a made-up score. The frontend adapter must show "unknown" neutrally.

Issues come from Findings that overlap the section (their label and metric),
so every issue shown traces back to something detected.
"""

from dataclasses import dataclass, field

import librosa
import numpy as np

from app.analyzers.interfaces import (
    AlignmentResult,
    AnalyzerOutput,
    AudioFeatures,
    Finding,
    PITCH_ACCURACY,
    STABILITY,
)
from app.core.logging import get_logger
from app.utils.audio_utils import linear_score

log = get_logger("naadamaya.analyzers.sections")

HOP_LENGTH = 4096
TARGET_SECTION_SECONDS = 40.0
MIN_SECTION_SECONDS = 5.0
SINGLE_SECTION_BELOW_SECONDS = 20.0
MIN_SECTIONS, MAX_SECTIONS = 2, 8
SNAP_DISTANCE_SECONDS = 3.0
MIN_GAP_TO_SNAP_SECONDS = 0.4

MIN_PITCH_FRAMES = 20
MIN_PATH_POINTS = 3
MIN_CONFIDENCE = 0.5
MAX_PLAUSIBLE_CENTS = 400.0

GOOD_SCORE, WARNING_SCORE = 75.0, 60.0
MAX_ISSUES = 3

ISSUE_TYPES = {
    "pitch_accuracy": "pitch",
    "melody_matching": "melody",
    "rhythm": "timing",
    "stability": "stability",
    "expression": "dynamics",
    "breath_control": "breath",
    "pronunciation": "pronunciation",
}


@dataclass
class SectionResult:
    key: str
    name: str
    start: float
    end: float
    score: float | None = None
    pitch_score: float | None = None
    timing_score: float | None = None
    stability_score: float | None = None
    status: str = "unknown"          # good | warning | critical | unknown
    issues: list[dict] = field(default_factory=list)   # [{"type", "label"}]
    note: str | None = None
    is_estimated: bool = True

    def to_model_fields(self) -> dict:
        """Keyword arguments for the AnalysisSection database model."""
        return {
            "section_key": self.key,
            "section_name": self.name,
            "start_time": round(self.start, 2),
            "end_time": round(self.end, 2),
            "score": None if self.score is None else round(self.score, 1),
            "pitch_score": None if self.pitch_score is None else round(self.pitch_score, 1),
            "timing_score": None if self.timing_score is None else round(self.timing_score, 1),
            "stability_score": None if self.stability_score is None else round(self.stability_score, 1),
            "status": self.status,
            "issues": self.issues,
            "note": self.note,
            "is_estimated": self.is_estimated,
        }


# ==========================================================
# Finding the boundaries
# ==========================================================
def _span(reference: AudioFeatures) -> tuple[float, float]:
    if reference.active_regions:
        start, end = float(reference.active_regions[0][0]), float(reference.active_regions[-1][1])
        if end - start >= 3.0:
            return start, end
    return 0.0, float(reference.duration)


def _even_boundaries(start: float, end: float, count: int) -> list[float]:
    return [float(t) for t in np.linspace(start, end, count + 1)[1:-1]]


def _detected_boundaries(reference: AudioFeatures, start: float, end: float, count: int) -> list[float] | None:
    """Section starts found from changes in the original's timbre, or None if that fails."""
    try:
        sr = reference.sample_rate
        y = reference.samples[int(start * sr): int(end * sr)]
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=HOP_LENGTH)
        if mfcc.shape[1] < count * 4:
            return None
        mfcc = (mfcc - mfcc.mean(axis=1, keepdims=True)) / (mfcc.std(axis=1, keepdims=True) + 1e-6)
        frames = librosa.segment.agglomerative(mfcc, count)
        times = start + librosa.frames_to_time(np.asarray(frames), sr=sr, hop_length=HOP_LENGTH)
        return [float(t) for t in times[1:]]
    except Exception:  # noqa: BLE001 - structure detection is optional
        log.info("section detection failed, using an even split")
        return None


def _snap_to_pauses(boundaries: list[float], regions: list[tuple[float, float]]) -> list[float]:
    """Moves a boundary to the middle of a nearby pause, so sections do not cut a phrase."""
    gaps = [
        (a_end, b_start)
        for (_, a_end), (b_start, _) in zip(regions, regions[1:])
        if b_start - a_end >= MIN_GAP_TO_SNAP_SECONDS
    ]
    snapped = []
    for t in boundaries:
        best = None
        for g_start, g_end in gaps:
            mid = (g_start + g_end) / 2.0
            if abs(mid - t) <= SNAP_DISTANCE_SECONDS and (best is None or abs(mid - t) < abs(best - t)):
                best = mid
        snapped.append(best if best is not None else t)
    return snapped


def _clean(boundaries: list[float], start: float, end: float) -> list[float]:
    """Sorted, and no section shorter than MIN_SECTION_SECONDS."""
    kept: list[float] = []
    last = start
    for t in sorted(boundaries):
        if t - last >= MIN_SECTION_SECONDS and end - t >= MIN_SECTION_SECONDS:
            kept.append(t)
            last = t
    return kept


# ==========================================================
# Scoring one section
# ==========================================================
def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _pitch_score(alignment: AlignmentResult | None, start: float, end: float) -> float | None:
    aligned = alignment.aligned_pitch if alignment else None
    if aligned is None:
        return None
    mask = (
        (aligned.times >= start)
        & (aligned.times < end)
        & np.isfinite(aligned.deviation_cents)
        & (aligned.confidence >= MIN_CONFIDENCE)
        & (np.abs(aligned.deviation_cents) <= MAX_PLAUSIBLE_CENTS)
    )
    if int(mask.sum()) < MIN_PITCH_FRAMES:
        return None
    return linear_score(float(np.median(np.abs(aligned.deviation_cents[mask]))), best=10.0, worst=100.0)


def _timing_score(alignment: AlignmentResult | None, start: float, end: float) -> float | None:
    if alignment is None or len(alignment.path) < MIN_PATH_POINTS or alignment.quality < 0.25:
        return None
    path = np.asarray(alignment.path, dtype=float)
    mask = (path[:, 0] >= start) & (path[:, 0] < end)
    if int(mask.sum()) < MIN_PATH_POINTS:
        return None
    lag = path[mask, 1] - path[mask, 0] - float(alignment.start_offset)
    return linear_score(float(np.median(np.abs(lag))), best=0.08, worst=0.60)


def _stability_score(stability_notes: list[dict], start: float, end: float) -> float | None:
    inside = [n for n in stability_notes if start <= (n["start"] + n["end"]) / 2.0 < end]
    if not inside:
        return None
    return linear_score(float(np.median([n["spread_cents"] for n in inside])), best=15.0, worst=70.0)


def _issues(findings: list[Finding], start: float, end: float) -> list[dict]:
    chosen: list[tuple[float, dict]] = []
    seen: set[str] = set()
    for f in sorted(findings, key=lambda f: -f.severity):
        shared = _overlap(f.start, f.end, start, end)
        if shared <= 0:
            continue
        if shared < min(1.0, 0.5 * max(f.end - f.start, 0.01)) and shared < 0.3 * (end - start):
            continue  # only a sliver of this finding falls inside the section
        label = f.label or f.kind.replace("_", " ").capitalize()
        if label in seen:
            continue
        seen.add(label)
        chosen.append((f.severity, {"type": ISSUE_TYPES.get(f.metric_id, "other"), "label": label}))
    return [issue for _, issue in chosen[:MAX_ISSUES]]


def _status(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= GOOD_SCORE:
        return "good"
    if score >= WARNING_SCORE:
        return "warning"
    return "critical"


# ==========================================================
# The whole step
# ==========================================================
def build_sections(
    reference: AudioFeatures,
    outputs: list[AnalyzerOutput],
    alignment: AlignmentResult | None,
) -> list[SectionResult]:
    start, end = _span(reference)
    length = end - start
    if length <= 0:
        return []

    if length < SINGLE_SECTION_BELOW_SECONDS:
        edges = [start, end]
        names = ["Full song"]
    else:
        count = int(np.clip(round(length / TARGET_SECTION_SECONDS), MIN_SECTIONS, MAX_SECTIONS))
        found = _detected_boundaries(reference, start, end, count)
        boundaries = found if found is not None else _even_boundaries(start, end, count)
        boundaries = _snap_to_pauses(boundaries, reference.active_regions)
        boundaries = _clean(boundaries, start, end)
        edges = [start, *boundaries, end]
        names = [f"Section {i + 1}" for i in range(len(edges) - 1)]

    findings = [f for out in outputs for f in out.findings]

    stability_notes: list[dict] = []
    for out in outputs:
        if out.metric.metric_id == STABILITY and out.metric.available:
            stability_notes = list(out.details.get("notes", []))

    sections: list[SectionResult] = []
    for i, name in enumerate(names):
        s, e = edges[i], edges[i + 1]
        pitch = _pitch_score(alignment, s, e)
        timing = _timing_score(alignment, s, e)
        stab = _stability_score(stability_notes, s, e)

        parts = [v for v in (pitch, timing, stab) if v is not None]
        score = float(np.mean(parts)) if parts else None

        sections.append(
            SectionResult(
                key=f"section_{i + 1}" if len(names) > 1 else "full_song",
                name=name,
                start=s,
                end=e,
                score=score,
                pitch_score=pitch,
                timing_score=timing,
                stability_score=stab,
                status=_status(score),
                issues=_issues(findings, s, e),
                is_estimated=True,
            )
        )
    return sections
