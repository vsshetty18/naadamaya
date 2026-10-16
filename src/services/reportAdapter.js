/**
 * NAADAMAYA report adapter.
 *
 * The backend sends snake_case reports (see backend schemas/report.py). The
 * Report components were built against the camelCase shape of the mock data.
 * This file converts one into the other, so NO component changes.
 *
 *   const analysis = adaptReport(await getReport(id))       // sync, pure
 *   const { analysis, release } = await attachAudio(analysis) // optional, fetches audio
 *   const progress = adaptProgress(await getAnalysisStatus(id))
 *
 * Honesty rules kept here:
 *   - Nothing is invented. A missing block stays null or empty, so the Report
 *     page draws no card for it.
 *   - overallScore may be null (too little was measured). Components already
 *     show a dash for that.
 *   - Metrics that could not be measured arrive in `unavailableMetrics`, never
 *     in `metrics`.
 *   - The only made-up value is the DECORATIVE cover tile for a song with no
 *     artwork (a gradient picked from the song id). It carries no data.
 *   - Pitch values stay in MIDI numbers, and the axis uses the same scale, so
 *     the graph lines up. The axis labels are plain note names (C4, D4...),
 *     not Sa/Re/Ga: the MVP cannot know the singer's tonic.
 */

import { fetchMediaUrl } from '@/services/api/library'

/* ==========================================================
   Decorative cover (no data in it)
   ========================================================== */
const COVERS = [
  ['#F2B880', '#B9695A', '#3B4A66'],
  ['#F3D9A4', '#C99A5B', '#7A4726'],
  ['#F4C58A', '#D98A4B', '#7C3A2A'],
  ['#CBD9C1', '#6F8F6A', '#2F4A3A'],
  ['#CCE1E7', '#5B9AAC', '#255C6E'],
]
const MOTIFS = ['mountains', 'lamp', 'temple']

function coverFor(id = '') {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0
  return { gradient: COVERS[h % COVERS.length], motif: MOTIFS[h % MOTIFS.length] }
}

/* ==========================================================
   Small helpers
   ========================================================== */
const num = (v) => (v === null || v === undefined || v === '' || !Number.isFinite(Number(v)) ? null : Number(v))

function pitchSeries(points, key) {
  return (points || [])
    .filter((p) => num(p.t) !== null && num(p[key]) !== null)
    .map((p) => ({ t: Number(p.t), v: Number(p[key]) }))
}

function adaptPitch(block) {
  if (!block) return null
  const originalPitchData = pitchSeries(block.points, 'ref_midi')
  const userPitchData = pitchSeries(block.points, 'user_midi')
  if (originalPitchData.length < 2 || userPitchData.length < 2) return null // the graph needs two lines

  const stats = block.stats
  return {
    axis: (block.axis || []).map((a) => ({ label: a.label, value: Number(a.value) })),
    originalPitchData,
    userPitchData,
    annotations: (block.annotations || []).map((a) => ({
      startTime: a.start_time,
      endTime: a.end_time,
      type: a.type,
      cents: a.cents,
      label: a.label,
    })),
    stats: stats
      ? {
          matchedPercent: num(stats.matched_percent),
          sharpPercent: num(stats.sharp_percent),
          flatPercent: num(stats.flat_percent),
        }
      : null,
    meanDeviationCents: num(block.mean_deviation_cents),
    notes: block.notes || [],
  }
}

/* ==========================================================
   The report
   ========================================================== */
export function adaptReport(report) {
  if (!report) return null
  const song = report.song || {}
  const rec = report.recording || {}
  const comparison = report.comparison || null

  return {
    songId: song.id,
    analysisId: report.analysis_id,
    createdAt: report.completed_at || report.created_at,
    attemptNumber: report.attempt_number,
    // The Report page shows a "Demo analysis" badge when meta.isMock is true.
    meta: { engineVersion: report.analysis_version, isMock: Boolean(report.is_simulated) },
    isSimulated: Boolean(report.is_simulated),

    overallScore: num(report.overall_score),
    statusLabel: report.status_label || null,
    summary: report.summary || null,

    original: {
      title: song.title,
      artist: song.artist || null,
      duration: num(song.duration) ?? 0,
      tempo: num(song.tempo),
      key: song.key || null,
      artwork: coverFor(song.id),
      waveform: song.waveform || [],
      audioUrl: null, // see attachAudio()
      audioPath: song.audio_url || null,
    },
    user: {
      displayName: null,
      avatarUrl: null,
      recordedAt: rec.recorded_at,
      duration: num(rec.duration) ?? 0,
      tempo: num(rec.tempo),
      waveform: rec.waveform || [],
      audioUrl: null,
      audioPath: rec.audio_url || null,
    },

    songProfile: report.song_profile
      ? { summary: report.song_profile.summary || null, tags: report.song_profile.tags || [] }
      : null,

    metrics: (report.metrics || []).map((m) => ({
      id: m.id,
      name: m.name,
      score: m.score,
      status: m.status,
      relevance: m.relevance,
      description: m.description,
      weight: m.weight,
      effectiveWeight: m.effective_weight,
    })),
    // Not rendered by the existing components. The Report page shows these as a short note.
    unavailableMetrics: (report.unavailable_metrics || []).map((m) => ({ id: m.id, name: m.name, reason: m.reason })),

    performance: report.performance || [],

    sections: (report.sections || []).map((s) => ({
      id: s.id,
      sectionName: s.name,
      startTime: s.start_time,
      endTime: s.end_time,
      score: num(s.score), // null when the section had nothing measurable
      status: s.status, // good | warning | critical | unknown
      issues: s.issues || [],
      note: s.note || null,
      isEstimated: Boolean(s.is_estimated),
    })),

    pitchComparison: adaptPitch(report.pitch_comparison),
    rhythmComparison: report.rhythm_comparison || null, // already {unit, entries}
    pronunciationAnalysis: report.pronunciation_analysis || null, // null until a recogniser exists
    breathAnalysis: report.breath_analysis || null, // already {phrases}

    insights: (report.insights || []).map((i) => ({
      type: i.type,
      title: i.title,
      description: i.description,
      evidence: i.evidence || {},
    })),
    recommendations: (report.recommendations || []).map((r) => ({
      id: r.id,
      priority: r.priority,
      title: r.title,
      description: r.description,
      metricId: r.metric_id,
      sectionId: r.section_id,
      duration: r.duration_minutes ? `${r.duration_minutes} min` : null,
    })),

    snapshot: (comparison?.snapshot || []).map((row) => ({
      id: row.id,
      label: row.label,
      format: row.format,
      original: row.original ?? null,
      user: row.user ?? null,
      difference: num(row.difference),
    })),

    previousAttempt: report.previous_attempt
      ? {
          attemptNumber: report.previous_attempt.attempt_number,
          score: num(report.previous_attempt.score),
          delta: num(report.previous_attempt.delta),
          metricDeltas: report.previous_attempt.metric_deltas || {},
        }
      : null,
    attemptHistory: (report.attempt_history || []).map((a) => ({
      attempt: a.attempt,
      score: num(a.score),
      date: a.date,
    })),
  }
}

/* ==========================================================
   Audio (needs the token on local storage)
   ========================================================== */
/**
 * Downloads the two audio files so the players can play them, and returns a
 * copy of the analysis with audioUrl filled in. Failures leave that player
 * without audio (it falls back to the silent simulated playhead).
 *
 * Call release() when leaving the report, to free the downloaded blobs.
 */
export async function attachAudio(analysis) {
  const created = []
  const load = async (path) => {
    try {
      const url = await fetchMediaUrl(path)
      if (url && url.startsWith('blob:')) created.push(url)
      return url
    } catch {
      return null
    }
  }

  const [originalUrl, userUrl] = await Promise.all([
    load(analysis.original.audioPath),
    load(analysis.user.audioPath),
  ])

  return {
    analysis: {
      ...analysis,
      original: { ...analysis.original, audioUrl: originalUrl },
      user: { ...analysis.user, audioUrl: userUrl },
    },
    release: () => created.forEach((u) => URL.revokeObjectURL(u)),
  }
}

/* ==========================================================
   Progress (for the ProcessingState screen)
   ========================================================== */
/**
 * Backend status -> the progress object ProcessingState reads:
 *   { status, stepIndex, totalSteps, stepId, label, percent }
 * The backend has 9 stages, the last one being COMPLETED, so the screen shows
 * the first 8 as steps (see analysisService, file 131).
 */
export function adaptProgress(status) {
  const total = Math.max(1, (status.total_steps || 9) - 1)
  const complete = status.status === 'COMPLETED'
  return {
    status: complete ? 'complete' : 'processing',
    stepIndex: complete ? total : Math.min(status.step_index || 0, total - 1),
    totalSteps: total,
    stepId: status.stage,
    label: status.stage_label,
    percent: complete ? 100 : status.progress || 0,
  }
}
