"""
NAADAMAYA MOCK analysis (ANALYSIS_MODE=mock).

FOR FRONTEND DEVELOPMENT ONLY. Nothing here measures any audio. It produces a
believable-looking result so the app can be built and demoed before the real
engine is trusted on real recordings.

Isolation rules:
  - This module is imported ONLY by the pipeline when settings.use_mock_analysis
    is true. config.py refuses to start in production with ANALYSIS_MODE=mock.
  - Every result is marked is_simulated=True and analysis_mode="mock", and its
    summary says it is simulated. The frontend shows a "Demo analysis" badge.
  - Results vary by song and attempt (seeded from the song and attempt ids) so
    different songs give visibly different reports, like the real engine will.
  - The real pipeline never calls anything in this file.

It returns the SAME structure the real pipeline produces (PipelineResult in
analysis_pipeline.py), so everything after it (saving, reports) is identical.
"""

import hashlib
import math
import random
import uuid
from typing import Any

from app.analyzers.interfaces import METRIC_NAMES, score_to_status

MOCK_NOTICE = "SIMULATED RESULT: generated for development, not measured from your audio."

# Different mock songs get different metric sets, like real songs would.
METRIC_SETS = [
    ["pitch_accuracy", "melody_matching", "rhythm", "stability", "expression"],
    ["pitch_accuracy", "rhythm", "stability", "breath_control"],
    ["pitch_accuracy", "melody_matching", "rhythm", "expression", "breath_control"],
]


def _rng(song_id: uuid.UUID, attempt: int) -> random.Random:
    digest = hashlib.sha256(f"{song_id}:{attempt}".encode()).hexdigest()
    return random.Random(int(digest[:12], 16))


def _waveform(rng: random.Random, bars: int = 56) -> list[float]:
    return [round(max(0.1, min(1.0, 0.35 + 0.5 * abs(math.sin(i / 5.0 + rng.random())))), 2) for i in range(bars)]


def build_mock(song_id: uuid.UUID, attempt: int, duration: float) -> dict[str, Any]:
    rng = _rng(song_id, attempt)
    duration = max(30.0, float(duration or 180.0))

    # Scores creep upward with attempts, so progress tracking has something to show.
    base = min(88.0, rng.uniform(58, 76) + (attempt - 1) * rng.uniform(1.5, 4.0))
    ids = METRIC_SETS[int(hashlib.sha256(str(song_id).encode()).hexdigest()[:4], 16) % len(METRIC_SETS)]

    metrics = []
    for mid in ids:
        s = max(35.0, min(97.0, base + rng.uniform(-12, 12)))
        metrics.append({
            "metric_id": mid,
            "name": METRIC_NAMES[mid],
            "available": True,
            "score": round(s, 1),
            "status": score_to_status(s),
            "relevance": rng.choice(["high", "medium"]),
            "description": f"{MOCK_NOTICE}",
        })
    metrics.append({
        "metric_id": "pronunciation",
        "name": METRIC_NAMES["pronunciation"],
        "available": False,
        "score": None,
        "status": "unavailable",
        "relevance": "medium",
        "description": None,
        "unavailable_reason": "Pronunciation analysis unavailable for this recording.",
    })

    overall = round(sum(m["score"] for m in metrics if m["available"]) / len(ids), 1)

    count = rng.randint(3, 5)
    edges = [round(duration * i / count, 1) for i in range(count + 1)]
    sections = []
    for i in range(count):
        s = max(40.0, min(96.0, base + rng.uniform(-18, 14)))
        status = "good" if s >= 75 else "warning" if s >= 60 else "critical"
        sections.append({
            "section_key": f"section_{i + 1}",
            "section_name": f"Section {i + 1}",
            "start_time": edges[i],
            "end_time": edges[i + 1],
            "score": round(s, 1),
            "pitch_score": None,
            "timing_score": None,
            "stability_score": None,
            "status": status,
            "issues": [] if status == "good" else [{"type": "pitch", "label": "Simulated issue"}],
            "note": None,
            "is_estimated": True,
        })

    # A simple simulated pitch curve (semitones above a made-up tonic).
    points = []
    steps = 120
    for i in range(steps):
        t = duration * i / (steps - 1)
        ref = 7 + 4 * math.sin(i / 9.0) + 2 * math.sin(i / 3.7)
        user = ref + rng.uniform(-0.45, 0.45)
        points.append({
            "t": round(t, 2),
            "ref_hz": round(261.63 * 2 ** (ref / 12), 1),
            "user_hz": round(261.63 * 2 ** (user / 12), 1),
            "ref_midi": round(60 + ref, 2),
            "user_midi": round(60 + user, 2),
            "deviation_cents": round((user - ref) * 100),
            "confidence": 0.9,
        })

    worst = min((m for m in metrics if m["available"]), key=lambda m: m["score"])
    best = max((m for m in metrics if m["available"]), key=lambda m: m["score"])
    insights = [
        {"type": "positive", "title": f"{best['name']} is strongest (simulated)",
         "description": MOCK_NOTICE, "priority": 0, "evidence": {"simulated": True}},
        {"type": "improvement", "title": f"{worst['name']} needs the most work (simulated)",
         "description": MOCK_NOTICE, "priority": 1, "evidence": {"simulated": True}},
    ]
    recommendations = [{
        "title": f"Practise {worst['name'].lower()} (simulated)",
        "description": MOCK_NOTICE,
        "priority": 1,
        "metric_type": worst["metric_id"],
        "section_key": None,
        "duration_minutes": 10,
    }]

    return {
        "overall_score": overall,
        "summary": MOCK_NOTICE,
        "metrics": metrics,
        "sections": sections,
        "pitch_points": points,
        "annotations": [],
        "pitch_stats": {"matched_percent": None, "sharp_percent": None, "flat_percent": None},
        "snapshot": [
            {"id": "duration", "label": "Duration", "format": "time",
             "original": round(duration, 1), "user": round(duration, 1), "difference": 0.0}
        ],
        "insights": insights,
        "performance": [{"type": "improvement", "text": MOCK_NOTICE}],
        "recommendations": recommendations,
        "reference_waveform": _waveform(rng),
        "user_waveform": _waveform(rng),
        "extras": {},
    }
