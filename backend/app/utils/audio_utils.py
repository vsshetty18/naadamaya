"""
NAADAMAYA audio math helpers.

Pure NumPy functions with no I/O: no FFmpeg, no files, no database. The
analyzers (pitch, rhythm, stability, ...) and the report generator share
these, so a conversion like "Hz to cents" is written once and tested once.

Pitch conventions used everywhere in NAADAMAYA:
  - Hz       frequency of the voice
  - MIDI     69 = A4 = 440 Hz, 60 = C4 (middle C)
  - cents    1/100 of a semitone. +100 cents = one semitone sharp.
  - notes    scientific pitch notation, sharps only: "C3", "A#4"

Unvoiced or unreliable frames are NaN, never 0, so a gap can never be
mistaken for a very low note.
"""

import math
import re

import numpy as np

A4_HZ = 440.0
A4_MIDI = 69

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_NOTE_BASE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d)$")


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


# ==========================================================
# Pitch conversions
# ==========================================================
def hz_to_midi(hz):
    """Hz to fractional MIDI. Works on numbers and arrays. Invalid input gives NaN."""
    arr = np.asarray(hz, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(arr > 0, A4_MIDI + 12.0 * np.log2(arr / A4_HZ), np.nan)
    return float(out) if out.ndim == 0 else out


def midi_to_hz(midi):
    arr = np.asarray(midi, dtype=float)
    out = A4_HZ * np.power(2.0, (arr - A4_MIDI) / 12.0)
    return float(out) if out.ndim == 0 else out


def cents_between(user_hz, reference_hz):
    """
    Signed distance of the singer from the reference, in cents.
    Positive = sharp (higher than the reference), negative = flat.
    """
    u = np.asarray(user_hz, dtype=float)
    r = np.asarray(reference_hz, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where((u > 0) & (r > 0), 1200.0 * np.log2(u / r), np.nan)
    return float(out) if out.ndim == 0 else out


def midi_to_note_name(midi: float) -> str | None:
    """60 -> 'C4'. The nearest note is used. NaN gives None."""
    if midi is None or not math.isfinite(midi):
        return None
    rounded = int(round(midi))
    return f"{_NOTE_NAMES[rounded % 12]}{rounded // 12 - 1}"


def hz_to_note_name(hz: float) -> str | None:
    midi = hz_to_midi(hz)
    return midi_to_note_name(midi) if np.isfinite(midi) else None


def note_name_to_midi(note: str) -> int | None:
    """'C4' -> 60, 'Bb2' -> 46. Invalid text gives None."""
    match = _NOTE_RE.match((note or "").strip())
    if not match:
        return None
    letter, accidental, octave = match.groups()
    value = _NOTE_BASE[letter.upper()] + (1 if accidental == "#" else -1 if accidental == "b" else 0)
    return (int(octave) + 1) * 12 + value


def note_name_to_hz(note: str) -> float | None:
    midi = note_name_to_midi(note)
    return None if midi is None else float(midi_to_hz(midi))


# ==========================================================
# Scoring helper
# ==========================================================
def linear_score(value: float, best: float, worst: float) -> float:
    """
    Maps a measurement to 0..100. `best` scores 100, `worst` scores 0, and
    values in between are on a straight line. Works whichever is larger, so
    it handles both "smaller error is better" and "larger is better".

        linear_score(error_cents, best=10, worst=100)
    """
    if best == worst or not math.isfinite(value):
        return 0.0
    fraction = (value - worst) / (best - worst)
    return clamp(fraction * 100.0)


# ==========================================================
# Safe statistics (return None, not a fake number, when data is missing)
# ==========================================================
def valid_values(values) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    return arr[np.isfinite(arr)]


def safe_mean(values, min_count: int = 1) -> float | None:
    arr = valid_values(values)
    return float(arr.mean()) if arr.size >= min_count else None


def safe_median(values, min_count: int = 1) -> float | None:
    arr = valid_values(values)
    return float(np.median(arr)) if arr.size >= min_count else None


def safe_std(values, min_count: int = 2) -> float | None:
    arr = valid_values(values)
    return float(arr.std()) if arr.size >= min_count else None


def percentile(values, q: float, min_count: int = 1) -> float | None:
    arr = valid_values(values)
    return float(np.percentile(arr, q)) if arr.size >= min_count else None


# ==========================================================
# Time series helpers
# ==========================================================
def contiguous_regions(mask, min_length: int = 1) -> list[tuple[int, int]]:
    """
    Runs of True in a boolean array, as (start_index, end_index_exclusive).
    Used to find voiced regions, sustained notes and unstable stretches.

        contiguous_regions([0,1,1,0,1], 1) -> [(1, 3), (4, 5)]
    """
    arr = np.asarray(mask, dtype=bool)
    if arr.size == 0:
        return []
    padded = np.concatenate(([False], arr, [False]))
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    starts, ends = changes[::2], changes[1::2]
    return [(int(s), int(e)) for s, e in zip(starts, ends) if e - s >= min_length]


def frames_to_time(frame_index, hop_length: int, sample_rate: int):
    """Frame index (or array of them) to seconds."""
    return np.asarray(frame_index, dtype=float) * hop_length / float(sample_rate)


def downsample_indices(length: int, max_points: int) -> np.ndarray:
    """Evenly spaced indices so a long curve can be sent to the graph at a sensible size."""
    if length <= 0:
        return np.array([], dtype=int)
    if length <= max_points:
        return np.arange(length)
    return np.unique(np.linspace(0, length - 1, max_points).round().astype(int))


def waveform_peaks(samples, bars: int = 56, floor: float = 0.08) -> list[float]:
    """
    Peak amplitude per slice of the audio, scaled to `floor`..1. This feeds the
    waveform bars in the Report players, so it comes from the real audio.
    """
    y = np.abs(np.asarray(samples, dtype=float))
    if y.size == 0 or bars <= 0:
        return []
    chunks = np.array_split(y, min(bars, y.size))
    peaks = np.array([c.max() if c.size else 0.0 for c in chunks])
    top = peaks.max()
    if top <= 0:
        return [floor] * len(peaks)
    return [round(float(max(floor, v / top)), 3) for v in peaks]


def rms_db(samples, floor_db: float = -80.0) -> float:
    """Loudness of a block of samples in dB (relative to full scale)."""
    y = np.asarray(samples, dtype=float)
    if y.size == 0:
        return floor_db
    rms = float(np.sqrt(np.mean(np.square(y))))
    return floor_db if rms <= 0 else max(floor_db, 20.0 * math.log10(rms))


def format_duration(seconds: float | None) -> str:
    """261 -> '04:21'. Missing or invalid -> '--:--'."""
    if seconds is None or not math.isfinite(seconds) or seconds < 0:
        return "--:--"
    total = int(round(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"
