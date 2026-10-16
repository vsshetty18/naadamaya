/**
 * NAADAMAYA analysis API: start, progress, reports, history, usage, dashboard.
 *
 *   const started = await startAnalysis(recordingId)           // spends 1 credit
 *   const status  = await getAnalysisStatus(started.analysis_id)
 *   const done    = await waitForAnalysis(id, { onProgress })  // polls until finished
 *   const report  = await getReport(id)
 *
 * Starting returns at once. The audio work happens in a background worker, so
 * the app polls /status (waitForAnalysis does this) until status is COMPLETED
 * or FAILED, then fetches the report.
 *
 * Double-charge protection: every startAnalysis call sends an Idempotency-Key.
 * If you retry the SAME logical action (for example after a network error),
 * pass the same key back in so the server returns the existing analysis.
 */

import api, { ApiError, newIdempotencyKey } from '@/services/apiClient'

/* ---------------- start and progress ---------------- */
export function startAnalysis(recordingId, { songId, idempotencyKey } = {}) {
  const key = idempotencyKey || newIdempotencyKey()
  return api
    .post('/analysis/start', { recording_id: recordingId, song_id: songId }, { idempotencyKey: key })
    .then((data) => ({ ...data, idempotencyKey: key }))
}

export const getAnalysisStatus = (id, options) => api.get(`/analysis/${id}/status`, options)
export const getAnalysis = (id) => api.get(`/analysis/${id}`)
export const listAnalyses = (params = {}) => api.get(`/analysis${api.qs(params)}`)

const POLL_MS = 1500
const POLL_MAX_MS = 25 * 60 * 1000
const MAX_CONSECUTIVE_FAILURES = 5

/**
 * Polls until the analysis finishes. Resolves with the final status object.
 *   onProgress(status)   called whenever the status changes
 *   signal               an AbortSignal to stop waiting (the analysis itself keeps running)
 * Rejects with ApiError when polling fails repeatedly, or after the time limit.
 * A FAILED analysis RESOLVES (check status.status), so the caller can show its message.
 */
export async function waitForAnalysis(id, { onProgress, signal } = {}) {
  const started = Date.now()
  let failures = 0
  let last = null

  while (Date.now() - started < POLL_MAX_MS) {
    if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError')

    try {
      const status = await getAnalysisStatus(id, { signal })
      failures = 0
      if (!last || last.stage !== status.stage || last.progress !== status.progress || last.status !== status.status) {
        last = status
        onProgress?.(status)
      }
      if (status.status === 'COMPLETED' || status.status === 'FAILED') return status
    } catch (err) {
      if (err?.name === 'AbortError') throw err
      if (err instanceof ApiError && (err.status === 404 || err.status === 403 || err.status === 401)) throw err
      failures += 1
      if (failures >= MAX_CONSECUTIVE_FAILURES) throw err
    }
    await sleep(POLL_MS, signal)
  }
  throw new ApiError({ code: 'TIMEOUT', message: 'The analysis is taking longer than expected.' })
}

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(timer)
        reject(new DOMException('Cancelled', 'AbortError'))
      },
      { once: true }
    )
  })
}

/* ---------------- reports ---------------- */
export const getReport = (id) => api.get(`/reports/${id}`)
export const deleteReport = (id) => api.del(`/reports/${id}`)

/* ---------------- progress, usage, dashboard ---------------- */
export const getProgressOverview = () => api.get('/progress')
export const getProgressHistory = (params = {}) => api.get(`/progress/history${api.qs(params)}`)
export const getSongProgress = (songId) => api.get(`/progress/songs/${songId}`)

export const getUsage = () => api.get('/usage')
export const getUsageHistory = (params = {}) => api.get(`/usage/history${api.qs(params)}`)

export const getDashboard = () => api.get('/dashboard')
