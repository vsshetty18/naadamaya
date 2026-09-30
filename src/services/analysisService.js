import { ACCEPTED_EXTENSIONS } from '@/hooks/useAudioUpload'
import {
  mockAnalysisData,
  mockSongList,
  getMockAnalysis,
  DEFAULT_MOCK_KEY,
} from '@/data/mockAnalysisData'

/**
 * The ONLY place the UI talks to for analysis.
 *
 * Today:  analyzeSong() validates the two audio slots, plays out staged
 *         progress, and returns a MOCK analysis object.
 * Later:  swap the body of runMockAnalysis() for runRemoteAnalysis()
 *         (POST /api/analyze). Components, pages and context stay unchanged,
 *         because they only ever see the same analysis object shape.
 *
 * No analysis logic lives in UI components. This file does not measure
 * pitch, rhythm or anything else. It only serves mock results.
 */

/* ==========================================================
   CONFIG
   ========================================================== */

// Set VITE_USE_MOCK=false in .env once a real backend exists.
const USE_MOCK = import.meta.env?.VITE_USE_MOCK !== 'false'
const API_BASE = import.meta.env?.VITE_API_BASE_URL || ''

/** The steps shown on the processing screen, in order. */
export const ANALYSIS_STEPS = [
  { id: 'listening', label: 'Listening to your performance...', ms: 900 },
  { id: 'pitch', label: 'Analyzing pitch...', ms: 950 },
  { id: 'melody', label: 'Comparing melody...', ms: 950 },
  { id: 'rhythm', label: 'Checking rhythm...', ms: 900 },
  { id: 'stability', label: 'Analyzing vocal stability...', ms: 900 },
  { id: 'report', label: 'Preparing your report...', ms: 800 },
]

export const COMPLETE_LABEL = 'Analysis complete.'

/* ==========================================================
   ERRORS
   ========================================================== */

/**
 * Codes the UI maps to polished error screens:
 *   audio_missing       one or both recordings were not provided
 *   unsupported_format  a file is not an audio format we accept
 *   analysis_failed     the engine could not finish
 *   network_error       the backend could not be reached
 *   timeout             the engine took too long
 *   cancelled           the user left or cancelled
 *   not_found           no analysis exists for the requested song
 */
export class AnalysisError extends Error {
  constructor(code, message, details = {}) {
    super(message || code)
    this.name = 'AnalysisError'
    this.code = code
    this.details = details // e.g. { slot: 'original' }
  }
}

export function isAnalysisError(err) {
  return err instanceof AnalysisError
}

/* ==========================================================
   HELPERS
   ========================================================== */

/** Waits `ms`, but rejects straight away if the signal is aborted. */
function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new AnalysisError('cancelled', 'Analysis was cancelled.'))
      return
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    const onAbort = () => {
      clearTimeout(timer)
      reject(new AnalysisError('cancelled', 'Analysis was cancelled.'))
    }
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

function extensionOf(name = '') {
  const match = /\.([^.]+)$/.exec(name)
  return match ? match[1].toLowerCase() : ''
}

/** True when the slot holds something we can analyse. */
function hasAudio(audio) {
  if (!audio) return false
  // A simulated recording has no file, but it is still a valid slot.
  return Boolean(audio.url || audio.file || audio.blob || audio.simulated)
}

function isSupported(audio) {
  if (audio.simulated) return true
  if (audio.mimeType) return audio.mimeType.startsWith('audio/')
  return ACCEPTED_EXTENSIONS.includes(extensionOf(audio.name))
}

/** Throws the right AnalysisError, or returns quietly when both slots are valid. */
export function validateAudioInputs(originalAudio, userAudio) {
  if (!hasAudio(originalAudio)) {
    throw new AnalysisError('audio_missing', 'The original song is missing.', { slot: 'original' })
  }
  if (!hasAudio(userAudio)) {
    throw new AnalysisError('audio_missing', 'Your voice recording is missing.', { slot: 'user' })
  }
  if (!isSupported(originalAudio)) {
    throw new AnalysisError('unsupported_format', 'The original song is not a supported audio format.', { slot: 'original' })
  }
  if (!isSupported(userAudio)) {
    throw new AnalysisError('unsupported_format', 'Your recording is not a supported audio format.', { slot: 'user' })
  }
}

/** Small stable hash so the same file always maps to the same mock report. */
function hashString(text = '') {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

/**
 * MOCK ONLY. Chooses which of the three demo reports to return, so different
 * uploads give visibly different reports. A real backend makes no such choice.
 */
function pickMockKey(originalAudio, userAudio, requestedKey) {
  if (requestedKey && mockAnalysisData[requestedKey]) return requestedKey
  const keys = Object.keys(mockAnalysisData)
  const seed = `${originalAudio?.name || ''}|${originalAudio?.size || 0}|${userAudio?.size || 0}`
  if (!originalAudio?.name) return DEFAULT_MOCK_KEY
  return keys[hashString(seed) % keys.length]
}

let analysisCounter = 0

function cloneAnalysis(source) {
  return typeof structuredClone === 'function'
    ? structuredClone(source)
    : JSON.parse(JSON.stringify(source))
}

/**
 * Gives a mock result a fresh identity and attaches the playable audio the
 * user actually provided, so the Report players can play their real files.
 */
function personalizeMock(source, originalAudio, userAudio) {
  const analysis = cloneAnalysis(source)
  analysisCounter += 1

  analysis.analysisId = `an_${Date.now().toString(36)}_${analysisCounter}`
  analysis.createdAt = new Date().toISOString()
  analysis.user.recordedAt = analysis.createdAt

  if (originalAudio?.url) analysis.original.audioUrl = originalAudio.url
  if (userAudio?.url) analysis.user.audioUrl = userAudio.url

  return analysis
}

/* ==========================================================
   analyzeSong: the main entry point
   ========================================================== */

/**
 * @param {object} originalAudio  audio slot from Learn: { name, url, file, duration, mimeType, size, simulated }
 * @param {object} userAudio      same shape
 * @param {object} [options]
 * @param {(p: object) => void} [options.onProgress]  called as each step starts
 * @param {AbortSignal} [options.signal]              cancels the run
 * @param {string} [options.mockKey]                  force songA / songB / songC (mock only)
 * @param {'failure'|'timeout'|'network'} [options.simulate]  force an error (mock only, for demos)
 * @returns {Promise<object>} an analysis object (see mockAnalysisData for the shape)
 */
export async function analyzeSong(originalAudio, userAudio, options = {}) {
  validateAudioInputs(originalAudio, userAudio)

  return USE_MOCK
    ? runMockAnalysis(originalAudio, userAudio, options)
    : runRemoteAnalysis(originalAudio, userAudio, options)
}

/* ---------- MOCK ---------- */

async function runMockAnalysis(originalAudio, userAudio, options) {
  const { onProgress, signal, mockKey, simulate } = options
  const total = ANALYSIS_STEPS.length

  // Fail partway through, like a real engine would.
  const failAtStep = simulate ? 3 : -1

  for (let i = 0; i < total; i++) {
    const step = ANALYSIS_STEPS[i]

    if (i === failAtStep) {
      const codes = {
        failure: ['analysis_failed', 'We could not finish analysing this performance.'],
        timeout: ['timeout', 'The analysis took longer than expected.'],
        network: ['network_error', 'We could not reach Naadamaya. Check your connection.'],
      }
      const [code, message] = codes[simulate] || codes.failure
      throw new AnalysisError(code, message, { stepId: step.id })
    }

    onProgress?.({
      status: 'processing',
      stepIndex: i,
      totalSteps: total,
      stepId: step.id,
      label: step.label,
      percent: Math.round((i / total) * 100),
    })

    await sleep(step.ms, signal)
  }

  onProgress?.({
    status: 'complete',
    stepIndex: total,
    totalSteps: total,
    stepId: 'complete',
    label: COMPLETE_LABEL,
    percent: 100,
  })

  const key = pickMockKey(originalAudio, userAudio, mockKey)
  return personalizeMock(getMockAnalysis(key), originalAudio, userAudio)
}

/* ---------- REAL BACKEND (not built yet) ---------- */

/**
 * Placeholder for the future engine. Intended contract:
 *
 *   POST {API_BASE}/api/analyze     multipart/form-data
 *     original: <file>
 *     user:     <file>
 *   -> 200 { ...analysis }          same shape as mockAnalysisData entries
 *
 * Progress would come from polling or a stream (SSE / WebSocket) and feed
 * onProgress with the same { stepId, label, percent } objects.
 */
async function runRemoteAnalysis(originalAudio, userAudio, { signal } = {}) {
  const body = new FormData()
  body.append('original', originalAudio.file || originalAudio.blob)
  body.append('user', userAudio.file || userAudio.blob)

  let response
  try {
    response = await fetch(`${API_BASE}/api/analyze`, { method: 'POST', body, signal })
  } catch (err) {
    if (err?.name === 'AbortError') throw new AnalysisError('cancelled', 'Analysis was cancelled.')
    throw new AnalysisError('network_error', 'We could not reach Naadamaya.')
  }

  if (!response.ok) {
    throw new AnalysisError('analysis_failed', 'The analysis could not be completed.', {
      status: response.status,
    })
  }
  return response.json()
}

/* ==========================================================
   Report song selector helpers
   ========================================================== */

/** Songs the user has already analysed (the Report dropdown). */
export async function listAnalyzedSongs() {
  await sleep(150)
  return mockSongList
}

/** Loads one existing analysis by key ("songA") or songId. */
export async function getAnalysis(keyOrId, { signal } = {}) {
  await sleep(350, signal)
  const found = getMockAnalysis(keyOrId)
  if (!found) {
    throw new AnalysisError('not_found', 'We could not find that analysis.')
  }
  return cloneAnalysis(found)
}
