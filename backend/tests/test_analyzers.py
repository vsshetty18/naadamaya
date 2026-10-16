"""
Analyzer unit tests: the audio math, alignment, and every analyzer, using
synthetic signals with KNOWN answers (a tone at a known pitch, a known delay,
a known number of cents sharp). No database or network is used (the conftest
autouse fixtures still run, so run these inside the container).

Most tests build the analyzers' inputs directly (pitch arrays, alignment
paths) so they are fast and exact. The alignment tests generate real audio
and run pYIN, so they take a few seconds each.
"""

import numpy as np
import pytest

from app.analyzers.alignment_engine import align
from app.analyzers.feedback_engine import RuleBasedFeedback
from app.analyzers.interfaces import (
    AlignedPitch,
    AlignmentResult,
    AnalysisInputs,
    AudioFeatures,
    Finding,
    MetricResult,
    PitchTrack,
)
from app.analyzers.melody_analyzer import SignalMelodyAnalyzer
from app.analyzers.pitch_analyzer import SignalPitchAnalyzer
from app.analyzers.pitch_extractor import get_pitch_extractor
from app.analyzers.pronunciation_analyzer import SignalPronunciationAnalyzer
from app.analyzers.rhythm_analyzer import SignalRhythmAnalyzer
from app.analyzers.scoring_engine import score
from app.analyzers.section_segmenter import build_sections
from app.analyzers.stability_analyzer import SignalStabilityAnalyzer
from app.core.exceptions import InvalidPhoneNumberError
from app.services.audio.preprocessing import find_active_regions
from app.utils.audio_utils import (
    cents_between,
    contiguous_regions,
    hz_to_midi,
    linear_score,
    midi_to_note_name,
    note_name_to_midi,
    waveform_peaks,
)
from app.utils.phone import mask_phone, normalize_phone

SR = 22050
HOP = 512 / SR   # seconds per pitch frame


# ==========================================================
# Helpers
# ==========================================================
def tone(freq: float, seconds: float) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    wave = 0.5 * np.sin(2 * np.pi * freq * t) + 0.15 * np.sin(2 * np.pi * 2 * freq * t)
    fade = np.minimum(1.0, np.minimum(t, seconds - t) / 0.02)   # no clicks
    return (wave * fade).astype("float32")


def melody(freqs, seconds_each=1.0, lead_silence=0.5) -> np.ndarray:
    silence = np.zeros(int(lead_silence * SR), dtype="float32")
    tail = np.zeros(int(0.5 * SR), dtype="float32")
    return np.concatenate([silence, *[tone(f, seconds_each) for f in freqs], tail])


def features(samples: np.ndarray, with_pitch=True) -> AudioFeatures:
    regions, _ = find_active_regions(samples, SR)
    f = AudioFeatures(
        samples=samples, sample_rate=SR, duration=len(samples) / SR, active_regions=regions
    )
    if with_pitch:
        f.pitch = get_pitch_extractor().extract(samples, SR)
    return f


def empty_features(seconds=2.0) -> AudioFeatures:
    return AudioFeatures(
        samples=np.zeros(int(seconds * SR), dtype="float32"),
        sample_rate=SR, duration=seconds, active_regions=[],
    )


SCALE = [220.0, 261.63, 329.63, 261.63, 220.0]


def aligned_from(ref_hz, user_hz, confidence=1.0) -> AlignedPitch:
    ref_hz, user_hz = np.asarray(ref_hz, float), np.asarray(user_hz, float)
    times = np.arange(len(ref_hz)) * HOP
    return AlignedPitch(
        times=times, ref_hz=ref_hz, user_hz=user_hz,
        deviation_cents=np.asarray(cents_between(user_hz, ref_hz), float),
        confidence=np.full(len(ref_hz), confidence), user_times=times,
    )


def inputs_with(aligned=None, details=None, notes=None, path=None, quality=0.9,
                start_offset=0.0, tempo_ratio=1.0, reference=None, user=None) -> AnalysisInputs:
    alignment = AlignmentResult(
        aligned_pitch=aligned, start_offset=start_offset, tempo_ratio=tempo_ratio,
        path=path or [], quality=quality, notes=notes or [], details=details or {},
    )
    return AnalysisInputs(reference=reference or empty_features(), user=user or empty_features(),
                          alignment=alignment)


# A 10-second melody of 43-frame notes (semitones above A3).
SEMIS = np.repeat([0, 4, 7, 4, 0, 5, 7, 9, 7, 4], 43)
REF_HZ = 220.0 * 2.0 ** (SEMIS / 12.0)


# ==========================================================
# Audio math
# ==========================================================
def test_pitch_conversions():
    assert hz_to_midi(440.0) == pytest.approx(69.0)
    assert midi_to_note_name(60) == "C4"
    assert note_name_to_midi("Bb2") == 46 and note_name_to_midi("C#4") == 61
    assert note_name_to_midi("H9") is None
    assert np.isnan(hz_to_midi(0.0))                      # silence is NaN, never "very low"


def test_cents_sign_sharp_is_positive():
    assert cents_between(440.0 * 2 ** (30 / 1200), 440.0) == pytest.approx(30.0)
    assert cents_between(440.0 * 2 ** (-30 / 1200), 440.0) == pytest.approx(-30.0)
    assert np.isnan(cents_between(0.0, 440.0))


def test_linear_score_and_regions():
    assert linear_score(10, best=10, worst=100) == 100
    assert linear_score(100, best=10, worst=100) == 0
    assert linear_score(55, best=10, worst=100) == pytest.approx(50.0)
    assert contiguous_regions([0, 1, 1, 0, 1], 1) == [(1, 3), (4, 5)]
    assert contiguous_regions([0, 1, 1, 0, 1], 2) == [(1, 3)]


def test_waveform_peaks_from_real_samples():
    peaks = waveform_peaks(tone(220, 2.0), bars=20)
    assert len(peaks) == 20 and max(peaks) == 1.0 and min(peaks) >= 0.08


# ==========================================================
# Phone numbers
# ==========================================================
def test_phone_formats_normalise_to_one_value():
    forms = ["+919876500001", "98765 00001", "919876500001", "09876500001", "+91-98765-00001"]
    assert {normalize_phone(f).e164 for f in forms} == {"+919876500001"}


def test_invalid_phone_numbers():
    for bad in ("12345", "abcdefghij", "", "+91 12345 67890"):
        with pytest.raises(InvalidPhoneNumberError):
            normalize_phone(bad)


def test_mask_phone_hides_digits():
    masked = mask_phone("+919876500001")
    assert masked.endswith("01") and "98765" not in masked


# ==========================================================
# Pitch analyzer
# ==========================================================
def test_perfect_singing_scores_high():
    out = SignalPitchAnalyzer().analyze(inputs_with(aligned_from(REF_HZ, REF_HZ)))
    assert out.metric.available and out.metric.score >= 95
    assert out.details["stats"]["matched_percent"] == 100
    assert out.findings == []


def test_constant_30_cents_sharp_lowers_score_but_is_not_flagged():
    user = REF_HZ * 2 ** (30 / 1200)
    out = SignalPitchAnalyzer().analyze(inputs_with(aligned_from(REF_HZ, user)))
    assert 70 < out.metric.score < 85            # median error 30 cents
    assert out.details["mean_deviation_cents"] == 30


def test_sharp_stretch_is_found_with_measured_cents():
    user = REF_HZ.copy()
    user[172:344] = REF_HZ[172:344] * 2 ** (60 / 1200)    # about 4 s to 8 s
    out = SignalPitchAnalyzer().analyze(inputs_with(aligned_from(REF_HZ, user)))
    sharp = [f for f in out.findings if f.kind == "pitch_sharp"]
    assert sharp, "a sharp stretch should be reported"
    assert 50 <= sharp[0].evidence["cents"] <= 70
    assert 3.4 <= sharp[0].start <= 4.6
    assert any(a["type"] == "sharp" for a in out.details["annotations"])
    assert 35 <= out.details["stats"]["sharp_percent"] <= 45


def test_flat_stretch_is_found():
    user = REF_HZ.copy()
    user[100:250] = REF_HZ[100:250] * 2 ** (-70 / 1200)
    out = SignalPitchAnalyzer().analyze(inputs_with(aligned_from(REF_HZ, user)))
    assert any(f.kind == "pitch_flat" and f.evidence["cents"] < -50 for f in out.findings)


def test_different_key_is_unavailable_not_a_low_score():
    out = SignalPitchAnalyzer().analyze(
        inputs_with(aligned_from(REF_HZ, REF_HZ * 2 ** (2 / 12)), details={"key_offset_semitones": 2.0})
    )
    assert out.metric.available is False and out.metric.score is None
    assert "different key" in out.metric.unavailable_reason


def test_no_alignment_is_unavailable_with_reason():
    out = SignalPitchAnalyzer().analyze(inputs_with(None, notes=["Not enough clear pitch was detected to compare notes."]))
    assert out.metric.available is False
    assert out.metric.unavailable_reason.startswith("Not enough clear pitch")


def test_too_little_data_is_unavailable():
    few = REF_HZ[:30]
    out = SignalPitchAnalyzer().analyze(inputs_with(aligned_from(few, few)))
    assert out.metric.available is False


def test_low_confidence_frames_are_ignored():
    out = SignalPitchAnalyzer().analyze(inputs_with(aligned_from(REF_HZ, REF_HZ, confidence=0.2)))
    assert out.metric.available is False


def test_tracking_garbage_is_unavailable():
    # an "octave of error" everywhere looks like tracking failure, not a 1200-cent singer
    out = SignalPitchAnalyzer().analyze(inputs_with(aligned_from(REF_HZ, REF_HZ * 2.0)))
    assert out.metric.available is False


# ==========================================================
# Melody analyzer
# ==========================================================
MEL_SEMIS = np.tile(np.repeat([0, 4, 7, 12], 22), 5)          # 440 frames, moves a lot
MEL_REF = 220.0 * 2.0 ** (MEL_SEMIS / 12.0)


def test_melody_is_key_independent():
    user = MEL_REF * 2 ** (2 / 12)                             # whole thing a tone higher
    out = SignalMelodyAnalyzer().analyze(inputs_with(aligned_from(MEL_REF, user)))
    assert out.metric.available and out.metric.score >= 95


def test_flat_singing_scores_badly_on_melody():
    user = np.full_like(MEL_REF, 440.0)                        # one note, no melody
    out = SignalMelodyAnalyzer().analyze(inputs_with(aligned_from(MEL_REF, user)))
    assert out.metric.available and out.metric.score < 20


def test_monotone_original_has_no_melody_to_compare():
    flat = np.full(400, 220.0)
    out = SignalMelodyAnalyzer().analyze(inputs_with(aligned_from(flat, flat)))
    assert out.metric.available is False
    assert "melodic movement" in out.metric.unavailable_reason


# ==========================================================
# Rhythm analyzer
# ==========================================================
def path(lag=0.0, scale=1.0):
    ref = np.arange(0, 30, 0.5)
    return [(float(r), float(r * scale + lag)) for r in ref]


def test_on_time_singing_scores_high():
    out = SignalRhythmAnalyzer().analyze(inputs_with(path=path(0.0)))
    assert out.metric.available and out.metric.score >= 95
    assert out.details["rhythm_comparison"]["unit"] == "ms"
    assert all(k in out.details["rhythm_comparison"]["entries"][0] for k in ("label", "startTime", "offsetMs"))


def test_late_singing_is_flagged_with_milliseconds():
    out = SignalRhythmAnalyzer().analyze(inputs_with(path=path(0.5)))
    assert out.metric.score < 30
    late = [f for f in out.findings if f.kind == "late_entry"]
    assert late and 450 <= late[0].evidence["offset_ms"] <= 550


def test_start_offset_is_not_counted_as_lateness():
    # the singer pressed record 3 seconds after the original began: not a mistake
    out = SignalRhythmAnalyzer().analyze(inputs_with(path=path(3.0), start_offset=3.0))
    assert out.metric.score >= 95 and out.findings == []


def test_growing_lag_is_reported_as_tempo_drift():
    out = SignalRhythmAnalyzer().analyze(inputs_with(path=path(0.0, scale=1.1), tempo_ratio=1.1))
    drift = [f for f in out.findings if f.kind == "tempo_drift"]
    assert drift and drift[0].evidence["direction"] == "slowing"


def test_poor_alignment_is_unavailable_rather_than_flattering():
    assert SignalRhythmAnalyzer().analyze(inputs_with(path=path(0.0), quality=0.1)).metric.available is False
    assert SignalRhythmAnalyzer().analyze(inputs_with(path=path(0.0)[:5])).metric.available is False


# ==========================================================
# Stability analyzer
# ==========================================================
def note_track(notes, noise_cents=0.0, vibrato=None, seed=1) -> PitchTrack:
    rng = np.random.default_rng(seed)
    chunks = []
    for hz in notes:
        n = 43
        cents = rng.normal(0, noise_cents, n) if noise_cents else np.zeros(n)
        if vibrato:
            cents = cents + vibrato * np.sin(2 * np.pi * 6.0 * np.arange(n) * HOP)
        chunks.append(hz * 2.0 ** (cents / 1200.0))
        chunks.append(np.full(5, np.nan))
    hz = np.concatenate(chunks)
    return PitchTrack(times=np.arange(len(hz)) * HOP, hz=hz, confidence=np.ones(len(hz)), method="test")


def stability_inputs(track) -> AnalysisInputs:
    user = empty_features()
    user.pitch = track
    return AnalysisInputs(reference=empty_features(), user=user)


def test_steady_notes_score_high():
    out = SignalStabilityAnalyzer().analyze(stability_inputs(note_track([220, 262, 330, 262])))
    assert out.metric.available and out.metric.score > 95


def test_wobbly_notes_score_lower():
    steady = SignalStabilityAnalyzer().analyze(stability_inputs(note_track([220, 262, 330, 262])))
    wobbly = SignalStabilityAnalyzer().analyze(stability_inputs(note_track([220, 262, 330, 262], noise_cents=35)))
    assert wobbly.metric.available and wobbly.metric.score < 85
    assert wobbly.metric.score < steady.metric.score - 15


def test_regular_vibrato_is_not_punished():
    out = SignalStabilityAnalyzer().analyze(stability_inputs(note_track([220, 262, 330, 262], vibrato=40)))
    assert out.metric.available and out.metric.score > 85
    assert out.details["vibrato_share"] > 0.5


def test_too_few_held_notes_is_unavailable():
    out = SignalStabilityAnalyzer().analyze(stability_inputs(note_track([220])))
    assert out.metric.available is False
    assert "held notes" in out.metric.unavailable_reason


def test_no_pitch_track_is_unavailable():
    assert SignalStabilityAnalyzer().analyze(AnalysisInputs(reference=empty_features(), user=empty_features())).metric.available is False


# ==========================================================
# Pronunciation: never faked
# ==========================================================
def test_pronunciation_is_always_unavailable_without_a_recogniser():
    out = SignalPronunciationAnalyzer().analyze(
        AnalysisInputs(reference=empty_features(), user=empty_features(), language="kannada", lyrics="some words here")
    )
    assert out.metric.available is False and out.metric.score is None
    assert out.metric.unavailable_reason == "Pronunciation analysis unavailable for this recording."


# ==========================================================
# Scoring
# ==========================================================
def m(metric_id, value, relevance="medium"):
    return MetricResult.measured(metric_id, value, relevance=relevance)


def test_weights_are_renormalised_over_measured_metrics():
    result = score([m("pitch_accuracy", 80), m("rhythm", 60), MetricResult.unavailable("pronunciation")])
    # configured 0.30 and 0.20 become 0.6 and 0.4
    assert result.overall == pytest.approx(72.0)
    assert sum(result.effective_weights.values()) == pytest.approx(1.0)
    pronunciation = next(x for x in result.metrics if x.metric_id == "pronunciation")
    assert pronunciation.effective_weight is None and pronunciation.score is None


def test_high_relevance_counts_more():
    plain = score([m("pitch_accuracy", 90), m("rhythm", 50)])
    focused = score([m("pitch_accuracy", 90), m("rhythm", 50, relevance="high")])
    assert focused.effective_weights["rhythm"] > plain.effective_weights["rhythm"]
    assert focused.overall < plain.overall


def test_one_measurement_is_not_an_overall_score():
    result = score([m("pitch_accuracy", 90)])
    assert result.overall is None and result.reason


def test_barely_any_coverage_is_not_an_overall_score():
    assert score([m("breath_control", 90), m("pronunciation", 90)]).overall is None


def test_different_metric_sets_give_different_scores():
    a = score([m("pitch_accuracy", 90), m("rhythm", 90), m("stability", 90)]).overall
    b = score([m("pitch_accuracy", 90), m("rhythm", 40), m("stability", 90)]).overall
    assert a > b


# ==========================================================
# Feedback: every sentence comes from a measurement
# ==========================================================
def test_feedback_uses_measured_numbers_and_times():
    metrics = [m("pitch_accuracy", 55), m("rhythm", 90)]
    findings = [Finding(kind="pitch_sharp", metric_id="pitch_accuracy", start=66, end=92,
                        severity=0.5, evidence={"cents": 32, "std_cents": 4})]
    fb = RuleBasedFeedback().generate(metrics, findings, {})
    improvement = next(i for i in fb["insights"] if i["type"] == "improvement")
    assert "32 cents" in improvement["description"] and "01:06" in improvement["description"]
    assert improvement["evidence"]["cents"] == 32
    assert any(i["type"] == "positive" and "Rhythm" in i["title"] for i in fb["insights"])
    assert fb["recommendations"][0]["metric_type"] == "pitch_accuracy"
    assert "01:06" in fb["recommendations"][0]["description"]


def test_no_praise_for_weak_performance_and_nothing_when_nothing_measured():
    weak = RuleBasedFeedback().generate([m("pitch_accuracy", 40)], [], {})
    assert not any(i["type"] == "positive" for i in weak["insights"])
    empty = RuleBasedFeedback().generate([MetricResult.unavailable("pitch_accuracy")], [], {})
    assert empty == {"insights": [], "performance": [], "recommendations": []}


# ==========================================================
# Sections
# ==========================================================
def test_short_song_is_one_unscored_section_without_data():
    ref = empty_features(10.0)
    ref.active_regions = [(0.0, 10.0)]
    sections = build_sections(ref, [], None)
    assert len(sections) == 1 and sections[0].name == "Full song"
    assert sections[0].score is None and sections[0].status == "unknown"   # never a made-up score
    assert sections[0].is_estimated is True


def test_section_gets_timing_score_from_the_alignment_path():
    ref = empty_features(10.0)
    ref.active_regions = [(0.0, 10.0)]
    alignment = AlignmentResult(aligned_pitch=None, start_offset=0.0, tempo_ratio=1.0,
                                path=[(float(i), float(i)) for i in range(11)], quality=0.9)
    section = build_sections(ref, [], alignment)[0]
    assert section.timing_score == 100 and section.status == "good"


# ==========================================================
# Alignment, with real audio and pYIN (slower)
# ==========================================================
@pytest.fixture(scope="module")
def reference_features():
    return features(melody(SCALE, lead_silence=0.5))


def test_alignment_finds_the_start_delay(reference_features):
    user = features(melody(SCALE, lead_silence=1.5))           # starts 1 second later
    result = align(reference_features, user)
    assert abs(result.start_offset - 1.0) < 0.3
    assert 0.9 < result.tempo_ratio < 1.1
    assert result.aligned_pitch is not None
    deviation = np.abs(result.aligned_pitch.deviation_cents)
    assert np.nanmedian(deviation) < 50
    assert abs(result.details["key_offset_semitones"]) < 0.7 and result.details["octave_shift"] == 0


def test_alignment_allows_for_an_octave_lower(reference_features):
    user = features(melody([f / 2 for f in SCALE], lead_silence=0.5))
    result = align(reference_features, user)
    assert result.details["octave_shift"] == -1
    assert any("octave" in n for n in result.notes)
    assert result.aligned_pitch is not None and np.nanmedian(np.abs(result.aligned_pitch.deviation_cents)) < 50


def test_alignment_reports_a_different_key_instead_of_hiding_it(reference_features):
    user = features(melody([f * 2 ** (3 / 12) for f in SCALE], lead_silence=0.5))
    result = align(reference_features, user)
    assert abs(result.details["key_offset_semitones"] - 3.0) < 0.6
    out = SignalPitchAnalyzer().analyze(AnalysisInputs(reference=reference_features, user=user, alignment=result))
    assert out.metric.available is False and "different key" in out.metric.unavailable_reason


def test_alignment_without_pitch_is_honest():
    a, b = empty_features(), empty_features()
    result = align(a, b)
    assert result.aligned_pitch is None and result.notes
