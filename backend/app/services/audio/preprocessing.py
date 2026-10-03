"""
NAADAMAYA audio preprocessing.

Turns a validated upload into an analysis-ready representation:

  1. FFmpeg converts it to a standard WAV: mono, ANALYSIS_SAMPLE_RATE, 16-bit.
  2. The WAV is loaded as float samples.
  3. Basic measurements are taken: loudness, peak, clipping, silence.
  4. Active (sound-carrying) regions are found.
  5. Quality warnings are collected (too quiet, clipped, mostly silent).

Rules:
  - The ORIGINAL upload is never modified. The converted WAV is a separate
    "processed" copy that the caller stores next to the original.
  - Audio is NOT cut and its amplitude is NOT normalised. Cutting would shift
    timestamps, and the timeline, pitch graph and section list must all refer
    to the same clock as the file the singer uploaded. Normalising would erase
    the loudness differences that expression analysis measures. Leading
    silence is reported (`leading_silence`) so the alignment step can
    compensate for it.
  - "Active regions" are found from signal energy only. They show WHERE there
    is sound, not whether it is a voice: a reference song with instruments is
    active everywhere. Separating the voice from the music is a future module
    (vocal separation) and is not claimed here.

Use prepared_audio() as a context manager so the temporary WAV is always
removed:

    with prepared_audio(local_path) as audio:
        audio.samples        # float32 mono array
        audio.wav_path       # processed WAV, store it before the block ends
        audio.metadata       # JSON-safe dict for the database
"""

import os
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import librosa
import numpy as np
import soundfile as sf

from app.core.config import settings
from app.core.exceptions import InvalidAudioError, ServiceUnavailableError
from app.core.logging import get_logger
from app.utils.audio_utils import (
    contiguous_regions,
    frames_to_time,
    rms_db,
    waveform_peaks,
)

log = get_logger("naadamaya.audio.preprocessing")

CONVERT_TIMEOUT_SECONDS = 180

FRAME_LENGTH = 2048
HOP_LENGTH = 512

# A frame counts as active when it is within ACTIVE_RANGE_DB of the loud parts,
# but never below the absolute floor (so background hiss is not "sound").
ACTIVE_RANGE_DB = 35.0
ACTIVE_FLOOR_DB = -55.0
MIN_ACTIVE_SECONDS = 0.12      # shorter blips are ignored
MERGE_GAP_SECONDS = 0.35       # pauses shorter than this do not split a region

# Quality thresholds
CLIPPING_WARN_RATIO = 0.001    # 0.1% of samples at full scale
QUIET_WARN_DB = -45.0          # overall loudness of the active parts
MOSTLY_SILENT_RATIO = 0.15     # less than 15% of the file has sound
NO_SOUND_RATIO = 0.01          # essentially silence: refuse to analyse


@dataclass
class PreparedAudio:
    samples: np.ndarray                      # float32, mono, untrimmed, unnormalised
    sample_rate: int
    duration: float                          # seconds
    wav_path: str                            # processed WAV (temporary)
    active_regions: list[tuple[float, float]]  # seconds, from signal energy
    leading_silence: float                   # seconds before the first active region
    trailing_silence: float
    metadata: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def active_duration(self) -> float:
        return float(sum(end - start for start, end in self.active_regions))

    def waveform(self, bars: int = 56) -> list[float]:
        """Bars for the Report player, drawn from the real audio."""
        return waveform_peaks(self.samples, bars=bars)


# ==========================================================
# Step 1: convert with FFmpeg
# ==========================================================
def convert_to_wav(source_path: str, dest_path: str, sample_rate: int | None = None) -> None:
    """
    Writes a mono 16-bit WAV at the analysis sample rate. The source is only read.
    Runs without a shell and with a timeout.
    """
    rate = sample_rate or settings.analysis_sample_rate
    cmd = [
        "ffmpeg", "-v", "error", "-nostdin", "-y",
        "-i", source_path,
        "-vn",                 # ignore cover art / video
        "-ac", "1",            # mono
        "-ar", str(rate),
        "-sample_fmt", "s16",
        "-f", "wav",
        dest_path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=CONVERT_TIMEOUT_SECONDS,
            check=False, shell=False,
        )
    except FileNotFoundError as exc:
        log.error("ffmpeg is not installed")
        raise ServiceUnavailableError("Audio processing is not available right now.") from exc
    except subprocess.TimeoutExpired as exc:
        raise InvalidAudioError("This audio file took too long to process.") from exc

    if result.returncode != 0 or not os.path.exists(dest_path) or os.path.getsize(dest_path) == 0:
        log.warning("ffmpeg conversion failed")
        raise InvalidAudioError("This audio file could not be converted.")


# ==========================================================
# Step 2: measurements
# ==========================================================
def _frame_db(samples: np.ndarray) -> np.ndarray:
    rms = librosa.feature.rms(y=samples, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH)[0]
    return 20.0 * np.log10(np.maximum(rms, 1e-10))


def _merge_close(regions: list[tuple[float, float]], max_gap: float) -> list[tuple[float, float]]:
    """Joins regions separated by a very short pause (a breath, a consonant)."""
    merged: list[tuple[float, float]] = []
    for start, end in regions:
        if merged and start - merged[-1][1] <= max_gap:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def find_active_regions(samples: np.ndarray, sample_rate: int) -> tuple[list[tuple[float, float]], float]:
    """
    Returns (regions_in_seconds, threshold_db). Based on energy only.
    """
    db = _frame_db(samples)
    if db.size == 0:
        return [], ACTIVE_FLOOR_DB

    loud = float(np.percentile(db, 95))
    threshold = max(loud - ACTIVE_RANGE_DB, ACTIVE_FLOOR_DB)

    frame_seconds = HOP_LENGTH / float(sample_rate)
    min_frames = max(1, int(round(MIN_ACTIVE_SECONDS / frame_seconds)))

    runs = contiguous_regions(db > threshold, min_length=min_frames)
    regions = [
        (
            float(frames_to_time(start, HOP_LENGTH, sample_rate)),
            float(frames_to_time(end, HOP_LENGTH, sample_rate)),
        )
        for start, end in runs
    ]
    return _merge_close(regions, MERGE_GAP_SECONDS), threshold


def _quality_warnings(
    samples: np.ndarray,
    active_ratio: float,
    active_loudness_db: float,
) -> list[str]:
    warnings: list[str] = []
    clipped = float(np.mean(np.abs(samples) >= 0.999)) if samples.size else 0.0
    if clipped > CLIPPING_WARN_RATIO:
        warnings.append("clipping")          # recorded too loud, distorted
    if active_loudness_db < QUIET_WARN_DB:
        warnings.append("very_quiet")        # pitch tracking may be less reliable
    if active_ratio < MOSTLY_SILENT_RATIO:
        warnings.append("mostly_silent")
    return warnings


# ==========================================================
# The whole step
# ==========================================================
@contextmanager
def prepared_audio(source_path: str) -> Iterator[PreparedAudio]:
    """
    Converts and measures the audio at `source_path`.
    The temporary WAV exists only inside the with-block: copy or store it there.
    """
    fd, wav_path = tempfile.mkstemp(prefix="naadamaya-processed-", suffix=".wav")
    os.close(fd)

    try:
        convert_to_wav(source_path, wav_path)

        try:
            samples, sample_rate = sf.read(wav_path, dtype="float32", always_2d=False)
        except (RuntimeError, sf.LibsndfileError) as exc:
            raise InvalidAudioError("This audio file could not be read.") from exc

        if samples.ndim > 1:  # defensive: FFmpeg already made it mono
            samples = samples.mean(axis=1)
        if samples.size == 0:
            raise InvalidAudioError("This audio file is empty.")

        duration = float(samples.size) / float(sample_rate)
        regions, threshold_db = find_active_regions(samples, sample_rate)

        active = float(sum(e - s for s, e in regions))
        active_ratio = active / duration if duration > 0 else 0.0
        if active_ratio < NO_SOUND_RATIO:
            raise InvalidAudioError("We could not hear any sound in this recording.")

        # Loudness of the parts that carry sound (silence would drag the average down).
        loud_chunks = [samples[int(s * sample_rate): int(e * sample_rate)] for s, e in regions]
        active_samples = np.concatenate(loud_chunks) if loud_chunks else samples
        active_db = rms_db(active_samples)

        leading = regions[0][0] if regions else 0.0
        trailing = max(0.0, duration - regions[-1][1]) if regions else 0.0

        warnings = _quality_warnings(samples, active_ratio, active_db)

        metadata = {
            "sample_rate": int(sample_rate),
            "channels": 1,
            "duration": round(duration, 3),
            "peak": round(float(np.max(np.abs(samples))), 4),
            "loudness_db": round(float(active_db), 1),
            "active_seconds": round(active, 2),
            "active_ratio": round(active_ratio, 3),
            "active_threshold_db": round(float(threshold_db), 1),
            "leading_silence": round(float(leading), 2),
            "trailing_silence": round(float(trailing), 2),
            "active_regions": [[round(s, 2), round(e, 2)] for s, e in regions],
            "active_regions_basis": "signal_energy",   # NOT voice detection
            "warnings": warnings,
        }

        yield PreparedAudio(
            samples=samples.astype(np.float32, copy=False),
            sample_rate=int(sample_rate),
            duration=duration,
            wav_path=wav_path,
            active_regions=regions,
            leading_silence=float(leading),
            trailing_silence=float(trailing),
            metadata=metadata,
            warnings=warnings,
        )
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass
