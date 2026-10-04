"""
NAADAMAYA alignment engine.

    result = align(reference, user)      # both are AudioFeatures with .pitch filled in

The singer may start late, sing slower or faster, or pause differently, so the
two recordings are never compared by simple subtraction. This module matches
them moment-to-moment with Dynamic Time Warping (DTW) and produces:

  - AlignedPitch: for each reference frame, the singer's pitch at the matching
    moment, on the REFERENCE clock (every later module uses this one clock)
  - start_offset: how many seconds after the reference the singer began
  - tempo_ratio: sung duration of the singer / sung duration of the reference
  - path: the matched (reference_seconds, user_seconds) points
  - quality: 0..1, how trustworthy the alignment is

How it works:
  1. Only the sound-carrying span of each recording is aligned (leading and
     trailing silence are excluded, and reported through start_offset).
  2. Each frame becomes a small feature vector: PITCH CLASS (a point on a
     circle, so an octave difference does not matter for matching) plus
     loudness. Loudness lets unvoiced stretches still line up.
  3. Features are averaged into blocks (about 0.09 s or more) so the DTW
     matrix stays small enough for long songs.
  4. DTW finds the cheapest path. When the two lengths are similar, steps are
     limited so the singer cannot be warped absurdly fast or slow.

Honesty rules:
  - If the pitch tracks are too weak to compare, aligned_pitch is None and the
    notes say why. Nothing is invented.
  - If the singer is an octave away from the reference, the octave is removed
    before measuring deviation (men often sing a female reference an octave
    lower), and details["octave_shift"] says so. Any remaining key difference is
    NOT removed: it is reported in details["key_offset_semitones"] so the pitch
    analyzer can decide whether pitch scoring is meaningful.
  - `quality` is a heuristic from how well the features match along the path.
    It is a confidence indicator, not a measured accuracy.
"""

import math

import librosa
import numpy as np

from app.analyzers.interfaces import AlignedPitch, AlignmentResult, AudioFeatures, PitchTrack
from app.analyzers.pitch_extractor import FRAME_LENGTH, HOP_LENGTH
from app.core.logging import get_logger
from app.utils.audio_utils import cents_between, hz_to_midi

log = get_logger("naadamaya.analyzers.alignment")

MAX_DTW_FRAMES = 2500          # per recording, after block averaging
MIN_BLOCK_FRAMES = 4           # about 0.09 s at the default hop
ENERGY_WEIGHT = 0.6
MIN_COMPARABLE_FRAMES = 40     # about 0.9 s of frames where both had a pitch
MIN_VOICED_RATIO = 0.08
SLOPE_LIMIT_RATIO = (0.6, 1.67)  # constrain the path only when lengths are this similar
MAX_PATH_POINTS = 200


# ==========================================================
# Helpers
# ==========================================================
def _span(features: AudioFeatures) -> tuple[float, float]:
    """Start and end (seconds) of the sound-carrying part."""
    if features.active_regions:
        return float(features.active_regions[0][0]), float(features.active_regions[-1][1])
    return 0.0, float(features.duration)


def _frame_range(track: PitchTrack, start: float, end: float) -> tuple[int, int]:
    i0 = int(np.searchsorted(track.times, start, side="left"))
    i1 = int(np.searchsorted(track.times, end, side="right"))
    return i0, max(i1, i0)


def _energy(features: AudioFeatures, n_frames: int) -> np.ndarray:
    """Loudness per pitch frame, scaled 0..1 against the recording's loud parts."""
    rms = librosa.feature.rms(
        y=features.samples, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH
    )[0]
    db = 20.0 * np.log10(np.maximum(rms, 1e-10))
    if db.size == 0:
        return np.zeros(n_frames)
    if db.size != n_frames:
        db = np.interp(np.linspace(0, db.size - 1, n_frames), np.arange(db.size), db)
    top = float(np.percentile(db, 95))
    return np.clip((db - (top - 40.0)) / 40.0, 0.0, 1.0)


def _feature_matrix(features: AudioFeatures, i0: int, i1: int) -> np.ndarray:
    """(3, frames): pitch-class cos, pitch-class sin, weighted loudness."""
    track = features.pitch
    hz = track.hz[i0:i1]
    with np.errstate(invalid="ignore"):
        midi = hz_to_midi(hz)
        angle = 2.0 * np.pi * np.mod(midi, 12.0) / 12.0
    cos = np.nan_to_num(np.cos(angle), nan=0.0)   # unvoiced frames become (0, 0)
    sin = np.nan_to_num(np.sin(angle), nan=0.0)
    energy = _energy(features, len(track))[i0:i1]
    return np.vstack([cos, sin, ENERGY_WEIGHT * energy])


def _block_mean(matrix: np.ndarray, step: int) -> np.ndarray:
    blocks = matrix.shape[1] // step
    if step <= 1 or blocks < 2:
        return matrix
    return matrix[:, : blocks * step].reshape(matrix.shape[0], blocks, step).mean(axis=2)


def _run_dtw(ref_f: np.ndarray, user_f: np.ndarray) -> np.ndarray | None:
    """Returns the warping path as an (N, 2) array in forward order, or None."""
    n, m = ref_f.shape[1], user_f.shape[1]
    if n < 2 or m < 2:
        return None

    ratio = m / n
    attempts = []
    if SLOPE_LIMIT_RATIO[0] <= ratio <= SLOPE_LIMIT_RATIO[1]:
        attempts.append(
            dict(
                step_sizes_sigma=np.array([[1, 1], [1, 2], [2, 1]]),
                weights_add=np.array([0.0, 0.0, 0.0]),
                weights_mul=np.array([1.0, 1.0, 1.0]),
                global_constraints=True,
                band_rad=0.35,
            )
        )
    attempts.append({})  # plain DTW as a fallback

    for options in attempts:
        try:
            _, wp = librosa.sequence.dtw(X=ref_f, Y=user_f, metric="euclidean", backtrack=True, **options)
            return np.asarray(wp)[::-1]
        except Exception:  # noqa: BLE001 - librosa raises ParameterError / ValueError when no path fits
            continue
    return None


# ==========================================================
# The alignment
# ==========================================================
def align(reference: AudioFeatures, user: AudioFeatures) -> AlignmentResult:
    notes: list[str] = []

    ref_start, ref_end = _span(reference)
    user_start, user_end = _span(user)
    start_offset = user_start - ref_start
    ref_len, user_len = ref_end - ref_start, user_end - user_start
    tempo_ratio = (user_len / ref_len) if ref_len > 0 and user_len > 0 else None

    if reference.pitch is None or user.pitch is None or ref_len <= 0 or user_len <= 0:
        notes.append("Insufficient data for reliable analysis.")
        return AlignmentResult(None, start_offset, tempo_ratio, [], 0.0, notes, {"reason": "missing_input"})

    ref_track, user_track = reference.pitch, user.pitch
    r0, r1 = _frame_range(ref_track, ref_start, ref_end)
    u0, u1 = _frame_range(user_track, user_start, user_end)
    if r1 - r0 < 4 or u1 - u0 < 4:
        notes.append("Insufficient data for reliable analysis.")
        return AlignmentResult(None, start_offset, tempo_ratio, [], 0.0, notes, {"reason": "too_short"})

    # ---- features and DTW ----
    ref_full = _feature_matrix(reference, r0, r1)
    user_full = _feature_matrix(user, u0, u1)
    step = max(MIN_BLOCK_FRAMES, math.ceil(max(ref_full.shape[1], user_full.shape[1]) / MAX_DTW_FRAMES))
    ref_ds, user_ds = _block_mean(ref_full, step), _block_mean(user_full, step)

    path = _run_dtw(ref_ds, user_ds)
    if path is None:
        notes.append("The two recordings could not be lined up reliably.")
        return AlignmentResult(None, start_offset, tempo_ratio, [], 0.0, notes, {"reason": "dtw_failed"})

    # Block index -> seconds (block centres), using the real frame times.
    def block_time(track: PitchTrack, first: int, k: np.ndarray) -> np.ndarray:
        idx = np.clip(first + (k + 0.5) * step, 0, len(track) - 1)
        return np.interp(idx, np.arange(len(track)), track.times)

    path_ref_t = block_time(ref_track, r0, path[:, 0].astype(float))
    path_user_t = block_time(user_track, u0, path[:, 1].astype(float))

    # Quality from how well the features match along the path.
    costs = np.linalg.norm(ref_ds[:, path[:, 0]] - user_ds[:, path[:, 1]], axis=0)
    mean_cost = float(costs.mean())
    quality = float(np.clip(1.0 - (mean_cost - 0.2) / 0.8, 0.0, 1.0))
    if tempo_ratio is not None and not (0.5 <= tempo_ratio <= 2.0):
        quality *= 0.5
        notes.append("The singing is much faster or slower than the original, so alignment is less certain.")

    # One singer time per reference time (mean), forced to move forward only.
    ref_unique, inverse = np.unique(path_ref_t, return_inverse=True)
    user_mean = np.bincount(inverse, weights=path_user_t) / np.bincount(inverse)
    user_mean = np.maximum.accumulate(user_mean)

    sample_idx = np.linspace(0, len(ref_unique) - 1, min(MAX_PATH_POINTS, len(ref_unique))).round().astype(int)
    path_points = [(round(float(ref_unique[i]), 3), round(float(user_mean[i]), 3)) for i in sample_idx]

    details: dict = {
        "method": "dtw",
        "block_frames": step,
        "mean_path_cost": round(mean_cost, 3),
        "reference_span": [round(ref_start, 2), round(ref_end, 2)],
        "user_span": [round(user_start, 2), round(user_end, 2)],
    }

    # ---- is there enough pitch on both sides to compare? ----
    ref_voiced = float(ref_track.hz[r0:r1].size and np.isfinite(ref_track.hz[r0:r1]).mean())
    user_voiced = float(user_track.hz[u0:u1].size and np.isfinite(user_track.hz[u0:u1]).mean())
    details["reference_voiced_ratio"] = round(ref_voiced, 3)
    details["user_voiced_ratio"] = round(user_voiced, 3)
    if ref_voiced < MIN_VOICED_RATIO or user_voiced < MIN_VOICED_RATIO:
        notes.append("Not enough clear pitch was detected to compare notes.")
        return AlignmentResult(None, start_offset, tempo_ratio, path_points, quality, notes, details)

    # ---- singer's pitch at each reference frame ----
    ref_times = ref_track.times[r0:r1]
    ref_hz = ref_track.hz[r0:r1]
    ref_conf = ref_track.confidence[r0:r1]

    user_times_for_ref = np.interp(ref_times, ref_unique, user_mean)
    hop = user_track.hop_seconds or 1.0
    nearest = np.clip(np.rint((user_times_for_ref - user_track.times[0]) / hop).astype(int), 0, len(user_track) - 1)
    user_hz = user_track.hz[nearest]
    user_conf = user_track.confidence[nearest]

    both = np.isfinite(ref_hz) & np.isfinite(user_hz)
    comparable = int(both.sum())
    details["comparable_frames"] = comparable
    if comparable < MIN_COMPARABLE_FRAMES:
        notes.append("Too little of the singing could be matched note-for-note.")
        return AlignmentResult(None, start_offset, tempo_ratio, path_points, quality, notes, details)

    # ---- remove an octave difference, keep (but report) any key difference ----
    with np.errstate(invalid="ignore", divide="ignore"):
        semitones = 12.0 * np.log2(user_hz[both] / ref_hz[both])
    median = float(np.median(semitones))
    octave_shift = int(round(median / 12.0))
    residual = median - 12.0 * octave_shift
    user_hz_adjusted = user_hz * (2.0 ** (-octave_shift))

    details["octave_shift"] = octave_shift
    details["key_offset_semitones"] = round(residual, 2)
    if octave_shift != 0:
        direction = "lower" if octave_shift < 0 else "higher"
        notes.append(f"You sang about {abs(octave_shift)} octave(s) {direction} than the original; this was allowed for.")
    if abs(residual) > 0.7:
        notes.append(f"You seem to be singing in a different key (about {residual:+.1f} semitones from the original).")

    deviation = np.asarray(cents_between(user_hz_adjusted, ref_hz), dtype=float)
    aligned = AlignedPitch(
        times=ref_times,
        ref_hz=ref_hz,
        user_hz=user_hz_adjusted,
        deviation_cents=deviation,
        confidence=np.minimum(ref_conf, user_conf),
        user_times=user_times_for_ref,
    )
    return AlignmentResult(aligned, start_offset, tempo_ratio, path_points, quality, notes, details)
