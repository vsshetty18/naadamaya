import {
  Music,
  Timer,
  Activity,
  Heart,
  MessageCircle,
  Wind,
  Sparkles,
  Mic,
  Waves,
  Mountain,
  TrendingUp,
  Target,
  Gauge,
  Layers,
  Clock,
  BarChart3,
  Ruler,
} from 'lucide-react'

/**
 * Presentation config for evaluation metrics.
 *
 * IMPORTANT: this file decides HOW a metric looks (icon + colour).
 * It never decides WHICH metrics appear or what their scores are.
 * The analysis response controls that. Unknown metric ids from a future
 * backend still render, using the FALLBACK below.
 */

/** Colour palettes. `color` is the bar/icon colour, `track` is the pale bar background. */
const PALETTE = {
  sage: { color: '#5F7F55', track: '#E3EBDD' },
  blue: { color: '#2F7186', track: '#E3EFF2' },
  amber: { color: '#C0892F', track: '#F6E9CC' },
  red: { color: '#C4574F', track: '#F8E7DD' },
  green: { color: '#5F9A6A', track: '#E3EFE3' },
  purple: { color: '#8A6BB0', track: '#EEE7F5' },
  copper: { color: '#B0703F', track: '#F5E4D5' },
  gold: { color: '#B98A42', track: '#F6E9CC' },
}

/** Known metrics. Keys match the `id` field the analysis engine returns. */
export const METRIC_CONFIG = {
  pitch_accuracy: { icon: Music, palette: PALETTE.sage },
  svara_accuracy: { icon: Music, palette: PALETTE.gold },
  melody_matching: { icon: Waves, palette: PALETTE.sage },
  rhythm: { icon: Timer, palette: PALETTE.blue },
  timing: { icon: Clock, palette: PALETTE.blue },
  tempo: { icon: Gauge, palette: PALETTE.blue },
  phrase_alignment: { icon: Layers, palette: PALETTE.blue },
  stability: { icon: Activity, palette: PALETTE.amber },
  vocal_stability: { icon: Activity, palette: PALETTE.amber },
  high_note_stability: { icon: TrendingUp, palette: PALETTE.amber },
  note_sustain: { icon: Ruler, palette: PALETTE.amber },
  vocal_range: { icon: Mountain, palette: PALETTE.copper },
  expression: { icon: Heart, palette: PALETTE.red },
  dynamics: { icon: BarChart3, palette: PALETTE.red },
  pronunciation: { icon: MessageCircle, palette: PALETTE.green },
  breath_control: { icon: Wind, palette: PALETTE.purple },
  ornamentation: { icon: Sparkles, palette: PALETTE.copper },
  pitch_transitions: { icon: Target, palette: PALETTE.sage },
}

/** Alternate ids a backend might send, mapped to our canonical ids. */
const ALIASES = {
  pitch: 'pitch_accuracy',
  svara: 'svara_accuracy',
  melody: 'melody_matching',
  rhythm_timing: 'rhythm',
  rhythm_and_timing: 'rhythm',
  breath: 'breath_control',
  breath_support: 'breath_control',
  vibrato: 'ornamentation',
  gamaka: 'ornamentation',
  lyrics: 'pronunciation',
  diction: 'pronunciation',
  range: 'vocal_range',
}

/** Used for any metric id we have not listed. Never crashes, never empty. */
const FALLBACK = { icon: Mic, palette: PALETTE.gold }

/** "some_new_metric" -> "Some New Metric". Used when a metric has no name. */
export function humanizeId(id = '') {
  return String(id)
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

/** Normalises any incoming id to a canonical key. */
export function resolveMetricId(id = '') {
  const key = String(id).toLowerCase().trim()
  return ALIASES[key] || key
}

/**
 * Presentation info for a metric.
 * Returns { id, icon, color, track } and always succeeds.
 */
export function getMetricConfig(id) {
  const canonical = resolveMetricId(id)
  const entry = METRIC_CONFIG[canonical] || FALLBACK
  return {
    id: canonical,
    icon: entry.icon,
    color: entry.palette.color,
    track: entry.palette.track,
  }
}

/** Display name: the backend's name wins, otherwise a readable version of the id. */
export function getMetricName(metric = {}) {
  return metric.name || humanizeId(metric.id)
}

/**
 * Relevance controls emphasis only. It never hides a returned metric.
 * The report can use this to sort or subtly badge the most important ones.
 */
export const RELEVANCE_ORDER = { high: 0, medium: 1, low: 2 }

export function sortByRelevance(metrics = []) {
  return [...metrics].sort((a, b) => {
    const ra = RELEVANCE_ORDER[a.relevance] ?? 1
    const rb = RELEVANCE_ORDER[b.relevance] ?? 1
    return ra - rb
  })
}

/** Icons for Comparison Snapshot rows, keyed by the row id the backend returns. */
export const SNAPSHOT_ICONS = {
  key: Music,
  average_pitch: Music,
  tempo: Gauge,
  duration: Clock,
  pitch_deviation: Activity,
  stability: BarChart3,
  stability_score: BarChart3,
  vocal_range: Mountain,
  timing_offset: Timer,
}

export function getSnapshotIcon(id) {
  return SNAPSHOT_ICONS[String(id).toLowerCase()] || BarChart3
}
