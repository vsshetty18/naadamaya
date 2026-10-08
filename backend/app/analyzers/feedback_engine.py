"""
NAADAMAYA feedback engine.

    feedback = RuleBasedFeedback().generate(metrics, findings, context)

Turns MEASURED facts into plain-language insights, "How You Performed" lines
and practice recommendations. Rule-based today (FeedbackGenerator interface),
so an AI teacher can replace it later.

Rules:
  - Every sentence is built from a Finding (what, where, how big) or a
    measured MetricResult. No generic motivation, no random text.
  - Each insight carries `evidence`: the numbers and time range it came from.
  - A positive insight appears only when its metric was measured AND strong.
  - Recommendations target the weakest measured areas and the worst findings.
  - If nothing was measured well enough, the output is empty. It never
    pretends.

Returned dict:
  insights         [{type, title, description, priority, evidence}]
  performance      [{type, text}]       ("How You Performed")
  recommendations  [{title, description, priority, metric_type,
                     section_key, duration_minutes}]
"""

from typing import Any

from app.analyzers.interfaces import (
    BREATH_CONTROL,
    EXPRESSION,
    MELODY_MATCHING,
    PITCH_ACCURACY,
    RHYTHM,
    STABILITY,
    FeedbackGenerator,
    Finding,
    MetricResult,
)
from app.utils.audio_utils import format_duration

STRONG = 80.0
WEAK = 70.0
MAX_INSIGHTS_PER_KIND = 4
MAX_RECOMMENDATIONS = 4


def _when(f: Finding) -> str:
    return f"{format_duration(f.start)} to {format_duration(f.end)}"


def _sentence(f: Finding) -> tuple[str, str]:
    """(title, description) for one finding, using only its measured evidence."""
    e, when = f.evidence, _when(f)

    if f.kind == "pitch_sharp":
        return ("Pitch runs sharp", f"Between {when} you were about {abs(e.get('cents', 0))} cents above the original. "
                "Practise the phrase slowly and listen for the target note before adding speed.")
    if f.kind == "pitch_flat":
        return ("Pitch runs flat", f"Between {when} you were about {abs(e.get('cents', 0))} cents below the original. "
                "Hold the phrase slowly and match the target pitch before increasing tempo.")
    if f.kind == "pitch_unstable":
        return ("Pitch is unsteady", f"Between {when} your pitch moved around by about {e.get('std_cents', 0):.0f} cents.")
    if f.kind == "melody_mismatch":
        return ("Melody differs from the original",
                f"Between {when} your melody moved about {e.get('mean_gap_semitones', 0):.1f} semitones away from the original's.")
    if f.kind == "late_entry":
        return ("Entries are late", f"Between {when} you came in about {abs(e.get('offset_ms', 0))} ms after the original.")
    if f.kind == "early_entry":
        return ("Entries are early", f"Between {when} you came in about {abs(e.get('offset_ms', 0))} ms before the original.")
    if f.kind == "tempo_drift":
        way = "slowed down" if e.get("direction") == "slowing" else "sped up"
        return ("Tempo drifts", f"Across the song you {way}, ending about {abs(e.get('drift_seconds', 0)):.1f} seconds off the original's pace.")
    if f.kind == "tempo_off":
        way = "slower" if e.get("direction") == "slower" else "faster"
        return ("Tempo differs", f"You sang about {abs(e.get('tempo_ratio', 1) - 1) * 100:.0f}% {way} than the original.")
    if f.kind == "unstable_note":
        high = " in your higher notes" if e.get("high_note") else ""
        return ("Held notes waver" + high, f"Around {when} held notes wavered by about {e.get('spread_cents', 0)} cents.")
    if f.kind == "energy_flat":
        return ("Dynamics are flat", f"Between {when} the original varies in loudness by about {e.get('reference_variation_db', 0):.0f} dB; you varied by about {e.get('user_variation_db', 0):.0f} dB.")
    if f.kind == "breath_strained":
        return ("Phrase end weakens", f"The phrase at {when} ({e.get('phrase_seconds', 0):.0f} s) faded or sagged toward the end.")
    return (f.label or "Needs attention", f"Around {when}.")


RECOMMENDATION_TEXT = {
    PITCH_ACCURACY: ("Match the target pitch", "Sing the flagged phrases slowly alongside the original, then record again.", 8),
    MELODY_MATCHING: ("Follow the melody's shape", "Hum the original's line first, then sing it with words.", 8),
    RHYTHM: ("Tighten your timing", "Sing along at about 80% tempo and aim to start each line together with the original.", 8),
    STABILITY: ("Steady your held notes", "Hold long notes against a steady drone and keep them still.", 10),
    EXPRESSION: ("Shape your dynamics", "Mark where the original gets louder and softer, and follow that shape.", 6),
    BREATH_CONTROL: ("Support the end of phrases", "Practise the longest phrases on one breath at a slower pace, keeping the last note as firm as the first.", 8),
}


class RuleBasedFeedback(FeedbackGenerator):
    def generate(
        self,
        metrics: list[MetricResult],
        findings: list[Finding],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        measured = [m for m in metrics if m.available and m.score is not None]
        if not measured:
            return {"insights": [], "performance": [], "recommendations": []}

        insights: list[dict] = []
        performance: list[dict] = []

        # ---- strengths: only strong, measured metrics ----
        for m in sorted(measured, key=lambda m: -m.score)[:MAX_INSIGHTS_PER_KIND]:
            if m.score >= STRONG:
                insights.append({
                    "type": "positive",
                    "title": f"{m.name} is strong",
                    "description": m.description,
                    "priority": 0,
                    "evidence": {"metric": m.metric_id, "score": m.score, **m.evidence},
                })
                performance.append({"type": "positive", "text": m.description or f"{m.name} matched the original well."})

        # ---- improvements: worst findings first ----
        ranked = sorted(findings, key=lambda f: -f.severity)[:MAX_INSIGHTS_PER_KIND + 2]
        for i, f in enumerate(ranked, start=1):
            title, desc = _sentence(f)
            insights.append({
                "type": "improvement",
                "title": title,
                "description": desc,
                "priority": i,
                "evidence": {"kind": f.kind, "metric": f.metric_id, "start": f.start, "end": f.end, **f.evidence},
            })
            performance.append({"type": "issue" if f.severity >= 0.6 else "improvement", "text": desc})

        # weak metrics with no specific finding still deserve a note
        covered = {f.metric_id for f in ranked}
        for m in measured:
            if m.score < WEAK and m.metric_id not in covered:
                insights.append({
                    "type": "improvement",
                    "title": f"{m.name} needs work",
                    "description": m.description,
                    "priority": len(insights) + 1,
                    "evidence": {"metric": m.metric_id, "score": m.score, **m.evidence},
                })

        # ---- recommendations: weakest measured metrics ----
        recommendations: list[dict] = []
        for m in sorted(measured, key=lambda m: m.score):
            if m.score >= STRONG or m.metric_id not in RECOMMENDATION_TEXT:
                continue
            title, desc, minutes = RECOMMENDATION_TEXT[m.metric_id]
            worst = max((f for f in findings if f.metric_id == m.metric_id), key=lambda f: f.severity, default=None)
            if worst is not None:
                desc = f"{desc} Start with {_when(worst)}."
            recommendations.append({
                "title": title,
                "description": desc,
                "priority": len(recommendations) + 1,
                "metric_type": m.metric_id,
                "section_key": None,
                "duration_minutes": minutes,
                "start": worst.start if worst else None,
            })
            if len(recommendations) >= MAX_RECOMMENDATIONS:
                break

        return {"insights": insights, "performance": performance, "recommendations": recommendations}
