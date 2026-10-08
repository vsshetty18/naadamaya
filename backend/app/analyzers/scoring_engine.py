"""
NAADAMAYA scoring engine.

    scored = score(metrics, mode_weights=None)

Combines the metrics that were actually MEASURED into one overall score.

Rules (from the product spec):
  - Unavailable metrics are excluded. They get no score and no weight.
  - The configured weights of the remaining metrics are re-normalised so they
    add up to 1. Example: pitch 0.30, rhythm 0.20, stability 0.15 are the only
    ones measured -> effective weights 0.46, 0.31, 0.23.
  - Weights live HERE (WEIGHTS), not in the frontend, and can be changed in
    one place. They can also be overridden per call.
  - Relevance nudges a weight up or down: a metric the song depends on
    ("high") counts 1.25x, an incidental one ("low") 0.75x. This is how
    different songs get different reports from the same engine.
  - If fewer than MIN_METRICS metrics were measured, or too little of the
    configured weight is covered, there is NO overall score (None). A single
    weak measurement must not be presented as "your score".

The status label is NOT decided here. The frontend derives it from the score
(or uses a backend-supplied label later).
"""

from dataclasses import dataclass

from app.analyzers.interfaces import (
    BREATH_CONTROL,
    EXPRESSION,
    MELODY_MATCHING,
    PITCH_ACCURACY,
    PRONUNCIATION,
    RHYTHM,
    STABILITY,
    MetricResult,
)

# Configured importance of each metric. They need not add up to 1.
WEIGHTS: dict[str, float] = {
    PITCH_ACCURACY: 0.30,
    MELODY_MATCHING: 0.15,
    RHYTHM: 0.20,
    STABILITY: 0.15,
    EXPRESSION: 0.10,
    PRONUNCIATION: 0.05,
    BREATH_CONTROL: 0.05,
}

RELEVANCE_FACTOR = {"high": 1.25, "medium": 1.0, "low": 0.75}

MIN_METRICS = 2
MIN_COVERAGE = 0.35   # measured metrics must cover at least this share of the configured weight


@dataclass
class ScoreResult:
    overall: float | None
    metrics: list[MetricResult]          # same objects, with weight and effective_weight filled
    effective_weights: dict[str, float]
    coverage: float                      # share of configured weight that was measurable
    reason: str | None = None            # why overall is None, when it is


def score(
    metrics: list[MetricResult],
    weights: dict[str, float] | None = None,
) -> ScoreResult:
    table = weights or WEIGHTS
    total_configured = sum(table.values()) or 1.0

    measured = [m for m in metrics if m.available and m.score is not None]

    # Record the configured weight on every metric (also unavailable ones).
    for m in metrics:
        m.weight = round(table.get(m.metric_id, 0.0) / total_configured, 4)
        m.effective_weight = None

    adjusted = {
        m.metric_id: table.get(m.metric_id, 0.0) * RELEVANCE_FACTOR.get(m.relevance, 1.0)
        for m in measured
    }
    adjusted = {k: v for k, v in adjusted.items() if v > 0}
    measured = [m for m in measured if m.metric_id in adjusted]

    coverage = sum(table.get(m.metric_id, 0.0) for m in measured) / total_configured

    if len(measured) < MIN_METRICS:
        return ScoreResult(None, metrics, {}, coverage, "Too few measurements for a reliable overall score.")
    if coverage < MIN_COVERAGE:
        return ScoreResult(None, metrics, {}, coverage, "Too little of the performance could be measured.")

    total = sum(adjusted.values())
    effective = {k: v / total for k, v in adjusted.items()}
    for m in measured:
        m.effective_weight = round(effective[m.metric_id], 4)

    overall = sum(m.score * effective[m.metric_id] for m in measured)
    return ScoreResult(round(max(0.0, min(100.0, overall)), 1), metrics, effective, coverage)
