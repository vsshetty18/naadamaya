"""
NAADAMAYA pronunciation analyzer.

Implements PronunciationAnalyzer.

HONEST STATUS: the MVP has NO speech recogniser. Judging pronunciation needs
one (speech-to-text or phoneme alignment for Kannada, Hindi or English), and
singing is much harder to recognise than speech. Nothing in this project
contains such a model, so this analyzer does not produce a score.

It always returns:
    "Pronunciation analysis unavailable for this recording."

It never estimates, guesses or derives a pronunciation score from pitch,
loudness or anything else. A fake score would mislead singers.

How a real engine plugs in later (no other file changes):
  1. Write a class implementing PronunciationRecognizer below (for example a
     Whisper-based or Kaldi/MFA-based recogniser for Kannada, Hindi, English).
  2. Return it from get_recognizer().
  3. When a recogniser is present and reports enough confidence, this analyzer
     compares the sung transcript with the reference lyrics and returns a
     measured MetricResult plus findings (mispronounced words with times).

The reference lyrics (inputs.lyrics) are optional. Without them, even a good
recogniser has nothing to compare against, and the metric stays unavailable.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from app.analyzers.interfaces import (
    PRONUNCIATION,
    REASON_PRONUNCIATION,
    AnalysisInputs,
    AnalyzerOutput,
    Finding,
    MetricResult,
    PronunciationAnalyzer,
)
from app.utils.audio_utils import linear_score

MIN_RECOGNITION_CONFIDENCE = 0.6
SUPPORTED_LANGUAGES = {"kannada", "hindi", "english"}


@dataclass
class RecognizedWord:
    text: str
    start: float          # seconds in the singer's recording
    end: float
    confidence: float     # 0..1


class PronunciationRecognizer(ABC):
    """A speech/singing recogniser. None is installed in the MVP."""

    name: str = "base"

    @abstractmethod
    def supports(self, language: str | None) -> bool: ...

    @abstractmethod
    def transcribe(self, samples: np.ndarray, sample_rate: int, language: str | None) -> list[RecognizedWord]: ...


@lru_cache
def get_recognizer() -> PronunciationRecognizer | None:
    """No recogniser exists yet. Return one here when it does."""
    return None


def _normalize(word: str) -> str:
    return "".join(ch for ch in word.lower() if ch.isalnum())


class SignalPronunciationAnalyzer(PronunciationAnalyzer):
    def analyze(self, inputs: AnalysisInputs) -> AnalyzerOutput:
        recognizer = get_recognizer()

        # The honest MVP path: nothing can recognise the words.
        if recognizer is None:
            return AnalyzerOutput(MetricResult.unavailable(PRONUNCIATION, REASON_PRONUNCIATION))

        language = (inputs.language or "").strip().lower() or None
        if not inputs.lyrics or not recognizer.supports(language):
            return AnalyzerOutput(MetricResult.unavailable(PRONUNCIATION, REASON_PRONUNCIATION))

        try:
            words = recognizer.transcribe(inputs.user.samples, inputs.user.sample_rate, language)
        except Exception:  # noqa: BLE001 - a recogniser failure must not fail the analysis
            return AnalyzerOutput(MetricResult.unavailable(PRONUNCIATION, REASON_PRONUNCIATION))

        confident = [w for w in words if w.confidence >= MIN_RECOGNITION_CONFIDENCE]
        expected = [_normalize(w) for w in inputs.lyrics.split() if _normalize(w)]
        if not expected or len(confident) < max(5, len(words) // 2):
            return AnalyzerOutput(MetricResult.unavailable(PRONUNCIATION, REASON_PRONUNCIATION))

        # Simple word match, in order. A real implementation would use phoneme alignment.
        heard = [_normalize(w.text) for w in confident]
        expected_set = set(expected)
        matched = sum(1 for h in heard if h in expected_set)
        accuracy = matched / max(1, len(heard))
        score = linear_score(accuracy, best=0.95, worst=0.4)

        findings = [
            Finding(
                kind="word_mismatch",
                metric_id=PRONUNCIATION,
                start=round(w.start, 2),
                end=round(w.end, 2),
                severity=0.4,
                evidence={"heard": w.text},
                label="Unclear word",
            )
            for w in confident
            if _normalize(w.text) not in expected_set
        ][:6]

        metric = MetricResult.measured(
            PRONUNCIATION,
            score,
            f"About {accuracy * 100:.0f}% of the recognised words matched the lyrics.",
            relevance="high",
            evidence={"word_match_percent": round(accuracy * 100, 1), "words": len(heard)},
        )
        return AnalyzerOutput(metric=metric, findings=findings, details={"recognizer": recognizer.name})
