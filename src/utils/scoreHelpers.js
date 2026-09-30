import { clamp } from '@/utils/formatters'

/**
 * Turns a numeric score into a status, label and colour tokens.
 * The backend may supply its own status; these helpers are the fallback
 * so the UI never depends on a fixed message.
 */

/** Ordered high -> low. First band whose `min` is <= score wins. */
export const SCORE_BANDS = [
  {
    key: 'excellent',
    min: 90,
    label: 'Excellent!',
    short: 'Excellent',
    tone: 'good',
    message: 'Your performance closely matched the reference.',
  },
  {
    key: 'very_good',
    min: 80,
    label: 'Very Good!',
    short: 'Very Good',
    tone: 'good',
    message: 'A strong match with just a few areas to refine.',
  },
  {
    key: 'good',
    min: 70,
    label: 'Good Job!',
    short: 'Good',
    tone: 'good',
    message: 'A solid match. Keep practicing the highlighted areas.',
  },
  {
    key: 'needs_practice',
    min: 55,
    label: 'Needs Practice',
    short: 'Needs Practice',
    tone: 'warn',
    message: 'The basics are there. Focus on the areas below.',
  },
  {
    key: 'needs_improvement',
    min: 0,
    label: 'Needs Improvement',
    short: 'Needs Improvement',
    tone: 'bad',
    message: 'There is room to grow. Start with the practice steps below.',
  },
]

/** Tailwind class sets per tone. Full class names so Tailwind can detect them. */
export const TONE_STYLES = {
  good: {
    text: 'text-sage-600',
    bg: 'bg-sage-50',
    border: 'border-sage-200',
    solid: 'bg-sage-500',
    stroke: '#5F7F55',
    track: '#E3EBDD',
    hex: '#5F7F55',
  },
  warn: {
    text: 'text-status-warn',
    bg: 'bg-blush-50',
    border: 'border-blush-200',
    solid: 'bg-status-warn',
    stroke: '#D9862F',
    track: '#F8E7DD',
    hex: '#D9862F',
  },
  bad: {
    text: 'text-status-bad',
    bg: 'bg-blush-100',
    border: 'border-blush-300',
    solid: 'bg-status-bad',
    stroke: '#C4574F',
    track: '#F8E7DD',
    hex: '#C4574F',
  },
}

/** Returns the band object for a score. Unknown scores fall to the lowest. */
export function getScoreBand(score) {
  const s = clamp(score)
  return SCORE_BANDS.find((band) => s >= band.min) || SCORE_BANDS[SCORE_BANDS.length - 1]
}

/**
 * Full display info for a score.
 * If the backend supplies `overrideLabel`, it is used instead of ours.
 */
export function getScoreStatus(score, overrideLabel) {
  const band = getScoreBand(score)
  return {
    ...band,
    label: overrideLabel || band.label,
    styles: TONE_STYLES[band.tone],
  }
}

/** Maps a backend metric status string to a tone. Falls back to the score. */
export function getToneFromStatus(status, score) {
  switch (status) {
    case 'excellent':
    case 'very_good':
    case 'good':
      return 'good'
    case 'needs_practice':
    case 'needs_improvement':
    case 'warning':
      return 'warn'
    case 'poor':
    case 'critical':
      return 'bad'
    default:
      return getScoreBand(score).tone
  }
}

/** Tone styles for a metric: uses backend status when given, else the score. */
export function getMetricTone(status, score) {
  return TONE_STYLES[getToneFromStatus(status, score)]
}

/** Trend between two attempt scores. */
export function getTrend(previous, current) {
  const p = Number(previous)
  const c = Number(current)
  if (!Number.isFinite(p) || !Number.isFinite(c)) {
    return { direction: 'flat', delta: 0 }
  }
  const delta = Math.round(c - p)
  if (delta > 0) return { direction: 'up', delta }
  if (delta < 0) return { direction: 'down', delta }
  return { direction: 'flat', delta: 0 }
}

/** Lowest-scoring items first. Powers "What should you practice?" fallbacks. */
export function sortByWeakest(items = [], getScore = (item) => item.score) {
  return [...items].sort((a, b) => getScore(a) - getScore(b))
}

/** Rounded average of the numeric scores, or null when there are none. */
export function averageScore(items = [], getScore = (item) => item.score) {
  const scores = items.map(getScore).filter((v) => Number.isFinite(Number(v)))
  if (scores.length === 0) return null
  return Math.round(scores.reduce((sum, v) => sum + Number(v), 0) / scores.length)
}
