"""
NAADAMAYA pitch extraction.

    extractor = get_pitch_extractor()
    track = extractor.extract(samples, sample_rate)      # -> PitchTrack

Implements the PitchExtractor interface with librosa's pYIN. Because the rest
of the pipeline only sees PitchTrack, CREPE or Essentia can replace this later
by adding one class and changing get_pitch_extractor().

What the track contains:
  - hz: fundamental frequency per frame. NaN (never 0) where no reliable pitch
    was heard, so a gap cannot be mistaken for a very low note.
  - confidence: 0..1 per frame (pYIN's voicing probability).

Reliability rules (nothing here pretends to be perfect):
  - Frames below MIN_CONFIDENCE are discarded (set to NaN).
  - Very short voiced fragments (under MIN_VOICED_SECONDS) are discarded,
    because they are usually noise or consonants, not sung notes.
  - pYIN tracks ONE dominant pitch. On a reference song with instruments the
    dominant pitch may be an instrument, not the singer. The extractor cannot
    know this. The pitch analyzer therefore judges reliability from the data
    (how much was voiced, how confident) and returns "insufficient data"
    instead of a score when the track is weak.
  - Octave jumps are not corrected here. They are rare in pYIN's output but
    possible, and the analyzers treat a deviation larger than a plausible
    singing error as unreliable rather than as a real 1200-cent mistake.
"""

from functools import lru_cache

import librosa
import numpy as np

from app.analyzers.interfaces import PitchExtractor, PitchTrack
from app.core.logging import get_logger
from app.utils.audio_utils import contiguous_regions

log = get_logger("naadamaya.analyzers.pitch")

# Singing range tracked: about C2 (65 Hz) to C6 (1047 Hz). Covers bass to soprano.
FMIN_HZ = float(librosa.note_to_hz("C2"))
FMAX_HZ = float(librosa.note_to_hz("C6"))

FRAME_LENGTH = 2048
HOP_LENGTH = 512

MIN_CONFIDENCE = 0.5
MIN_VOICED_SECONDS = 0.07


class PyinPitchExtractor(PitchExtractor):
    name = "pyin"

    def extract(self, samples: np.ndarray, sample_rate: int) -> PitchTrack:
        y = np.asarray(samples, dtype=np.float32)

        # Too short to analyse: return an honest, fully unvoiced track.
        if y.size < FRAME_LENGTH:
            return self._empty(y.size, sample_rate)

        f0, voiced_flag, voiced_prob = librosa.pyin(
            y,
            fmin=FMIN_HZ,
            fmax=FMAX_HZ,
            sr=sample_rate,
            frame_length=FRAME_LENGTH,
            hop_length=HOP_LENGTH,
        )

        hz = np.asarray(f0, dtype=float)
        confidence = np.nan_to_num(np.asarray(voiced_prob, dtype=float), nan=0.0)
        confidence = np.clip(confidence, 0.0, 1.0)

        # Keep only frames pYIN called voiced AND was reasonably sure about.
        keep = np.asarray(voiced_flag, dtype=bool) & (confidence >= MIN_CONFIDENCE) & np.isfinite(hz)
        hz = np.where(keep, hz, np.nan)

        hop_seconds = HOP_LENGTH / float(sample_rate)
        hz = self._drop_short_fragments(hz, hop_seconds)

        times = librosa.frames_to_time(
            np.arange(hz.size), sr=sample_rate, hop_length=HOP_LENGTH
        )
        return PitchTrack(times=times, hz=hz, confidence=confidence, method=self.name)

    @staticmethod
    def _drop_short_fragments(hz: np.ndarray, hop_seconds: float) -> np.ndarray:
        """Removes voiced runs shorter than MIN_VOICED_SECONDS."""
        min_frames = max(1, int(round(MIN_VOICED_SECONDS / hop_seconds)))
        cleaned = hz.copy()
        voiced = np.isfinite(hz)
        for start, end in contiguous_regions(voiced, min_length=1):
            if end - start < min_frames:
                cleaned[start:end] = np.nan
        return cleaned

    @staticmethod
    def _empty(num_samples: int, sample_rate: int) -> PitchTrack:
        frames = max(1, num_samples // HOP_LENGTH)
        times = np.arange(frames) * HOP_LENGTH / float(sample_rate)
        return PitchTrack(
            times=times,
            hz=np.full(frames, np.nan),
            confidence=np.zeros(frames),
            method="pyin",
        )


@lru_cache
def get_pitch_extractor() -> PitchExtractor:
    """The one place that decides which pitch engine is used."""
    return PyinPitchExtractor()
